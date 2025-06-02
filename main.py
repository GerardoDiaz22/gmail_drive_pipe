import os.path
import base64
import io
import email.utils
from typing import List, Dict, Any, Optional, Set
from datetime import datetime

# Google Drive API
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.auth.exceptions import RefreshError
from googleapiclient.http import MediaIoBaseUpload

# Libs for query expansion
from pattern.text.es import pluralize
from spellchecker import SpellChecker

spell = SpellChecker(language="es")

# If modifying these scopes, delete the file token.json.
SCOPES: List[str] = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/drive.file",
]

# Filters for the Gmail API search query
FILTERS: str = "in:inbox has:attachment"

# Directory where attachments will be saved
DRIVE_FOLDER: str = "Files"


# Custom classes for type hinting
class Attachment:
    def __init__(
        self, filename: str, data: bytes, mime_type: str, description: str = ""
    ):
        self.filename = filename
        self.data = data
        self.mime_type = mime_type
        self.description = description


def main():
    # Get the credentials for the Gmail API
    creds: Credentials = get_credentials()

    try:
        # Build the Gmail API service
        gmail_service: Any = build("gmail", "v1", credentials=creds)

        # Build the Drive API service
        drive_service: Any = build("drive", "v3", credentials=creds)

        # Get keywords from the user
        keywords: str = input(
            "Enter keywords to search for emails (separated by spaces): "
        ).strip()

        # Expand the keywords to include accents and plural forms
        expanded_keywords: List[str] = expand_query_keywords(keywords)

        # Add API filters for the search query
        query: str = " OR ".join(expanded_keywords) + " " + FILTERS

        print(f"Searching for emails with query: '{query}'")

        # Get all messages from the user's mailbox
        # "me" refers to the authenticated user
        res_msg_list: Dict[str, Any] = (
            gmail_service.users().messages().list(userId="me", q=query).execute()
        )
        msg_list: List[Dict[str, Any]] = res_msg_list.get("messages", [])

        # Iterate through the list of messages
        for msg_ref in msg_list:
            msg_id: str = msg_ref["id"]

            res_msg: Dict[str, Any] = (
                gmail_service.users()
                .messages()
                .get(userId="me", id=msg_id, format="full")
                .execute()
            )

            # Get the payload of the message
            msg_payload: Optional[Dict[str, Any]] = res_msg.get("payload")

            # TODO: Add pagination support if there are many messages

            if msg_payload:
                # Check if the payload has parts and extract the attachments
                # If it has parts, recursively extract the attachments
                # Otherwise, get the attachments directly
                attachments: List[Attachment] = get_attachments_from_parts(
                    gmail_service, msg_id, [msg_payload]
                )

                # Get mail details
                sender_name: str
                sender_email: str
                subject: str
                internalDate: Optional[str] = res_msg.get("internalDate")

                headers = msg_payload.get("headers", [])
                for header in headers:
                    if header["name"] == "From":
                        sender_name, sender_email = email.utils.parseaddr(
                            header["value"]
                        )
                        if not sender_name:
                            sender_name = "Unknown Sender"
                    if header["name"] == "Subject":
                        subject = header.get("value", "No Subject")

                # Convert internalDate to a human-readable formats
                month, year, timestamp = get_time_details(internalDate)

                # Define the desired folder path
                drive_folder_path: str = f"{DRIVE_FOLDER}/{year}/{month}"
                folder_names: List[str] = drive_folder_path.split("/")

                # Traverse or create the folder structure
                # Notice the parent_id is updated with each folder creation
                parent_id: Optional[str] = None
                for folder_name in folder_names:
                    parent_id = find_or_create_folder(
                        drive_service, folder_name, parent_id
                    )

                # If there are attachments, save them to the drive folder
                for attachment in attachments:
                    # Change attachment details
                    attachment.filename = (
                        f"({sender_name}) ({timestamp}) ({attachment.filename})"
                    )
                    attachment.description = f"Email from {sender_name}_{sender_email} with subject '{subject}'"

                    # Save attachment to user's Google Drive
                    save_file_to_drive(drive_service, attachment, parent_id)

    except HttpError as error:
        print(f"An error occurred: {error}")


# Function provided by Google Developers to create or retrieve credentials for the API
def get_credentials() -> Credentials:
    creds = None

    # If a token.json file exists, load the credentials from it
    # They can be invalid or expired
    if os.path.exists("token.json"):
        # The file token.json stores the user's access and refresh tokens, and is
        # created automatically when the authorization flow completes for the first
        # time.
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)

    # If there are no valid credentials available, let the user log in
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except RefreshError:
                print(
                    "Credentials have expired and cannot be refreshed. Trying to re-authenticate."
                )
                creds = None

        if not creds:
            flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
            creds = flow.run_local_server(port=0)

        # Save the credentials for the next run
        with open("token.json", "w") as token:
            token.write(creds.to_json())

    return creds  # type: ignore


# Function to expand query keywords by adding plural forms and spell-checked candidates
def expand_query_keywords(keywords_string: str) -> List[str]:
    expanded_keywords: List[str] = []

    for keyword in keywords_string.split():
        # Add the original keyword
        expanded_keywords.append(keyword)

        # Add plural form if it exists and is different from the original
        plural_form_original: str = pluralize(keyword)
        if plural_form_original and plural_form_original != keyword:
            expanded_keywords.append(plural_form_original)

        # Add spell-checked versions of the keyword
        # This will include the accented versions as well
        corrected_candidates: Optional[Set[str]] = spell.candidates(keyword)

        if corrected_candidates:
            # Add all spell-checked candidates
            expanded_keywords.extend(corrected_candidates)

            # Add plural form of each spell-checked version
            for corrected_word in corrected_candidates:
                plural_form_corrected: str = pluralize(corrected_word)
                if plural_form_corrected and plural_form_corrected != corrected_word:
                    expanded_keywords.append(plural_form_corrected)

    return expanded_keywords


# Recursively processes message parts to find and download attachments
def get_attachments_from_parts(
    gmail_service: Any,
    msg_id: str,
    parts: List[Dict[str, Any]],
    user_id: str = "me",
    attachments: Optional[List[Attachment]] = None,
) -> List[Attachment]:
    # Initialize the list of attachments if not provided
    if attachments is None:
        attachments = []

    """
    You, the reader, may think, "Why not just do `attachments = []`?"
    Well, Python evaluates default mutable arguments only once,
    so if we did that, it would keep adding to the same list
    every time the function is called, which is not what we want.
    And yes, I know, that's dumb, but that's how it is.
    """

    for part in parts:
        # Check if the part has a filename and attachmentId
        attachment_filename = part.get("filename")
        attachment_id = part.get("body", {}).get("attachmentId")

        if attachment_filename and attachment_id:
            # Get the attachment data using its ID
            res_attachment: Dict[str, Any] = (
                gmail_service.users()
                .messages()
                .attachments()
                .get(userId=user_id, messageId=msg_id, id=attachment_id)
                .execute()
            )

            # The attachment data is base64url encoded
            attachment_data = base64.urlsafe_b64decode(res_attachment["data"])

            # Determine the MIME type of the attachment
            attachment_mime_type = part.get("mimeType", "application/octet-stream")

            attachments.append(
                Attachment(attachment_filename, attachment_data, attachment_mime_type)
            )

        # If the part has nested parts, process them recursively
        if "parts" in part:
            get_attachments_from_parts(
                gmail_service, msg_id, part["parts"], user_id, attachments
            )

    return attachments


# Save the file to Google Drive
def save_file_to_drive(
    drive_service: Any, attachment: Attachment, folder_id: Optional[str] = None
):
    # Check if the file already exists in the target folder
    existing_file_id = check_file_existance_in_folder(
        drive_service, attachment.filename, folder_id
    )

    if existing_file_id:
        print(f"Skipping upload for '{attachment.filename}' as it already exists")
        return

    # Create a media object for the file
    media = MediaIoBaseUpload(
        io.BytesIO(attachment.data), mimetype=attachment.mime_type, resumable=True
    )

    # Create file metadata for Google Drive
    file_metadata: Dict[str, Any] = {
        "name": attachment.filename,
        "parents": [folder_id],
        "description": attachment.description,
    }

    # Upload the file to Google Drive
    file = (
        drive_service.files()
        .create(body=file_metadata, media_body=media, fields="id")
        .execute()
    )
    print(f"File '{attachment.filename}' saved to Drive with ID: {file.get('id')}")


# Find a folder by name in a specific parent folder. If it doesn't exist, creates it
def find_or_create_folder(drive_service, folder_name, parent_folder_id=None) -> str:
    # Build the search query
    # The MIME type is an special identifier for Google Drive folders
    query: str = (
        f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
    )

    # If parent_folder_id is provided, search within that folder
    # Otherwise, search in the root ('root' is an alias for the root folder ID in Google Drive)
    if parent_folder_id:
        query += f" and '{parent_folder_id}' in parents"
    else:
        query += " and 'root' in parents"

    res_folder_list: Dict[str, Any] = (
        drive_service.files()
        .list(q=query, spaces="drive", fields="files(id, name)")
        .execute()
    )

    folders: List[Dict[str, Any]] = res_folder_list.get("files", [])

    # Check if any folders were found. If so, return the first one
    # (We are assuming only one folder with that name exists)
    if folders:
        # Folder found, return its ID
        return folders[0]["id"]
    else:
        # Folder not found, create it
        print(f"Folder '{folder_name}' not found, creating...")
        file_metadata = {
            "name": folder_name,
            "mimeType": "application/vnd.google-apps.folder",
        }
        if parent_folder_id:
            file_metadata["parents"] = [parent_folder_id]

        folder = drive_service.files().create(body=file_metadata, fields="id").execute()
        print(f"Folder '{folder_name}' created with ID: {folder.get('id')}")
        return folder.get("id")


# Checks if a file with the given name exists in the specified folder
# Returns the file ID if it exists
def check_file_existance_in_folder(drive_service, filename, folder_id) -> Optional[str]:
    # Build the search query
    query: str = f"name='{filename}' and '{folder_id}' in parents and trashed=false"

    res_folder_list: Dict[str, Any] = (
        drive_service.files()
        .list(q=query, spaces="drive", fields="files(id, name)")
        .execute()
    )

    folders: List[Dict[str, Any]] = res_folder_list.get("files", [])

    return folders[0]["id"] if folders else None


# Helper function to get time details from internalDate
def get_time_details(internalDate: Optional[str]) -> tuple:
    try:
        if not internalDate:
            raise ValueError("internalDate is None or empty")

        dt = datetime.fromtimestamp(int(internalDate) / 1000)
        return (
            dt.strftime("%B"),
            dt.strftime("%Y"),
            dt.strftime("%H:%M:%S"),
        )
    except (ValueError, TypeError, OSError):
        return None, None, None


if __name__ == "__main__":
    main()
