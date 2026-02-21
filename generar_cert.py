"""Genera clave privada y CSR para certificado de produccion AFIP.

Pasos:
  1. Este script genera key.key y certificado.csr
  2. Subir el .csr al portal AFIP (ver instrucciones al final)
  3. Descargar el .crt desde AFIP y guardarlo como certificado.crt

Uso: python generar_cert.py
"""

import os
import subprocess
import sys


def main():
    if os.path.exists("key.key"):
        resp = input("key.key ya existe. Sobreescribir? [s/N]: ").strip().lower()
        if resp != "s":
            print("Cancelado.")
            sys.exit(0)

    cuit = input("CUIT (sin guiones): ").strip()
    razon_social = input("Razon social o nombre completo: ").strip()

    if not cuit or not razon_social:
        print("ERROR: Todos los campos son obligatorios")
        sys.exit(1)

    subject = f"/C=AR/O={razon_social}/CN=wsfe/serialNumber=CUIT {cuit}"

    print("\nGenerando clave privada (key.key)...")
    subprocess.run(
        ["openssl", "genrsa", "-out", "key.key", "2048"],
        check=True,
    )

    print("Generando CSR (certificado.csr)...")
    subprocess.run(
        ["openssl", "req", "-new", "-key", "key.key", "-out", "certificado.csr", "-subj", subject],
        check=True,
    )

    print(f"""
{'='*60}
  Archivos generados:
    - key.key         (clave privada - NO compartir)
    - certificado.csr (solicitud de certificado)
{'='*60}

  Pasos siguientes:

  1. Entrar a https://auth.afip.gob.ar/contribuyente/
  2. Ir a: Administracion de Certificados Digitales
     (buscar "certificados" en el buscador de servicios)
  3. Seleccionar "Computador Fiscal" o alias de tu equipo
  4. Click en "Crear certificado"
  5. Pegar el contenido de certificado.csr (o subir el archivo)
  6. Descargar el certificado generado y guardarlo como:
     certificado.crt (en esta misma carpeta)

  Luego ya podes usar main.py con PRODUCTION=true
{'='*60}
""")


if __name__ == "__main__":
    main()
