# Requisitos del proyecto
- Python 3.10.7 o superior.
- Gmail API y Google Drive API habilitadas en Google Cloud.
- Configuración de OAuth en Google Cloud.
- Credenciales de OAuth para la aplicación descargadas como `credentials.json`.

# Como ejecutar el proyecto
- Instalar las dependencias necesarias
```bash
pip install -r requirements.txt
```
- Instalar `pattern` desde su repositorio oficial

- Ejecutar la aplicación
```bash
py main.py
```

## Flujo de Ejecución
1. Autenticar al usuario para acceder a la API de Gmail y Google Drive.
2. Consultar los correos según los filtros proporcionados por el usuario.
3. Extraer los archivos adjuntos de los correos filtrados.
4. Guardar los archivos adjuntos en Google Drive, organizándolos según la fecha de recepción y el remitente.

## Características y posibles mejoras
- Agregar paginación para manejar grandes volúmenes de correos.
- Exponer etiquetas y filtros de búsqueda (in:inbox; has:attachment) al usuario.
- Permitir entrada de palabras clave para la búsqueda de correos.
- Expandir palabras clave para incluir plurales y acentos. La API de Gmail no realiza esta expansión, a diferencia del cliente web.
- Sustituir consulta dirigida a la API de Gmail por una consulta general y luego filtrar los correos según la entrada del usuario.
- Agregar interfaz gráfica.
- Mostrar progreso, archivos encontrados y preguntar confirmación al usuario antes de guardar archivos adjuntos.
- Agregar manejo de triggers para iniciar el programa al recibir nuevos correos y tomar acción sobre ellos.
- Agregar más escenarios de ejecución (guardar archivos adjuntos de correos bajo una etiqueta específica, correos de un remitente específico).
- Crear requeriments.txt para instalar dependencias.

## Consideraciones
- Al consultar hilos de correos, se repiten los archivos adjuntos obtenidos por la API. Estos archivos no se descartan para permitir que existan ediciones del archivo con el mismo nombre dentro del hilo. Sin embargo, puede llevar a duplicados si la edición no ocurre.
- Detalles para la configuración de la API de Gmail y Google Drive se pueden consultar aquí:
  - [Gmail API](https://developers.google.com/workspace/gmail/api/quickstart/python)
  - [Google Drive API](https://developers.google.com/workspace/drive/api/quickstart/python)
- Los limites de uso de la API de Gmail y Google Drive se pueden consultar aquí:
  - [Gmail API](https://developers.google.com/workspace/gmail/api/reference/quota.)
  - [Google Drive API](https://developers.google.com/workspace/gmail/api/reference/quota)
- El paquete 'pattern' ya no se encuentra disponible en PyPI, para instalarlo se deben seguir las instrucciones de su repositorio oficial [aquí](https://github.com/clips/pattern?tab=readme-ov-file#installation).