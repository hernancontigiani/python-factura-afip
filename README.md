
## Setup
Instalar las librerias necesarias

En caso de estar usando un virtual env activarlo con:
```
source venv/bin/activate
```


## Generar archivo .env (ejemplo)
```
# --- Modo ---
# false = homologacion/testing (default), true = produccion
PRODUCTION=false

# --- Obligatorios ---
CUIT=20409378472
ACCESS_TOKEN=xxxxxxx
PUNTO_VENTA=1

# --- CSV ---
# Separador de columnas del CSV de entrada y salida.
# Usar ";" en Windows si Excel genera punto y coma por defecto.
# CSV_SEPARATOR=,

# --- Solo produccion (ignorados en testing) ---
# Rutas a los archivos de certificado y clave privada
CERT_PATH=./certificado.crt
KEY_PATH=./key.key
```

## Configuración inicial
### Cuenta en Afip SDK
Se debe crear una cuetna en AFIP SDK para obtener un access token:
- https://app.afipsdk.com/


### Certificados
1- Generar el certificado CSR y la KEY usando generar_cert.py usando el CUIT y el nombre completo
2- Se debe ingresar a la pagina de AFIP y buscar el servicio "Administración de Certificados Digitales"
3- Cargar el certificado csr generado usando un alias cualquiera (ejemplo: facturador)
4- DEscargar el certificado .crt generado y colocarlo en esta carpeta, copiando el nombre del archivo en el archivo .env


Referencia:
- https://docs.afipsdk.com/recursos/tutoriales-pagina-de-arca/obtener-certificado-de-produccion

### Habilitar Web Service (WSASS)
- Se debe ingresar a la pagina de AFIP y buscar el servicio "Administrador de Relaciones de Clave Fiscal"
- Se debe elegir como servicio "wsfe - Facturación electrónica"

Referencia:
- https://docs.afipsdk.com/recursos/tutoriales-pagina-de-arca/autorizar-web-service-de-produccion


### Habilitar nuevo punto de venta
1- Se debe ingresar a la pagina de AFIP y buscar el servicio"Sistema registral"
2- Una vez allí en la pantalla de "Inicio" scrollear asia abajo hasta encontrar "Registro Úncio Tributario" y presionar "ingresar"
3- Esto abrirá una nueva pantalla en donde deberá scrollear asia abajo hasta la sección "Puntos de venta" y presionar modificar datos
4- Una vez allí presionar "agregar nuevo punto de venta" y elegir:
    - Modo de facturación: Factura Elétronica .... Web Services
5- Especificar el número del nuevo punto de venta que soporta WebService en el .env

Referencia:
- https://www.youtube.com/watch?v=Uumuf3X_6rk