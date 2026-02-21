"""Generador de Facturas Electronicas AFIP - Factura C (Monotributo)

Lee un CSV con datos de facturas, muestra resumen, pide confirmacion,
emite facturas tipo C via AFIP y genera CSV de resultados con CAE.

Uso: python main.py [facturas.csv]
"""

import csv
import os
import sys
from datetime import datetime

from afip import Afip
from dotenv import load_dotenv

# --- Constantes AFIP ---
CBTE_TIPO = 11       # Factura C
CONCEPTO = 2         # Servicios
DOC_TIPO = 96        # DNI
MONEDA_ID = "PES"    # Pesos argentinos
MONEDA_COTIZ = 1     # Cotizacion 1
IMP_TOT_CONC = 0     # Importe total conceptos no gravados
IMP_OP_EX = 0        # Importe operaciones exentas
IMP_IVA = 0          # Factura C no discrimina IVA
IMP_TRIB = 0         # Importe tributos
CONDICION_IVA_RECEPTOR = 5  # Consumidor Final (RG 5616)
DOC_TIPO_CONSUMIDOR_FINAL = 99  # Sin documento / Consumidor Final

load_dotenv()

# --- Configuracion desde .env ---
PRODUCTION = os.environ.get("PRODUCTION", "false").lower() == "true"
CUIT = int(os.environ["CUIT"])
ACCESS_TOKEN = os.environ["ACCESS_TOKEN"]
PUNTO_VENTA = int(os.environ["PUNTO_VENTA"])
CERT_PATH = os.environ.get("CERT_PATH", "")
KEY_PATH = os.environ.get("KEY_PATH", "")


def leer_csv(path):
    """Lee el CSV y devuelve lista de facturas con valores por defecto."""
    hoy = datetime.now().strftime("%Y%m%d")
    facturas = []

    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader, start=2):
            doc_nro = row.get("doc_nro", "").strip()
            imp_total = row.get("imp_total", "").strip()

            if not doc_nro or not imp_total:
                print(f"ERROR: Fila {i} incompleta (doc_nro={doc_nro!r}, imp_total={imp_total!r})")
                sys.exit(1)

            fecha = row.get("fecha", "").strip() or hoy
            es_final = doc_nro.lower() == "final"

            facturas.append({
                "doc_nro": None if es_final else int(doc_nro),
                "imp_total": float(imp_total),
                "fecha": fecha,
            })

    return facturas


def mostrar_resumen(facturas):
    """Muestra resumen de facturas y pide confirmacion."""
    print(f"\n{'='*60}")
    print(f"  RESUMEN DE FACTURAS A EMITIR")
    print(f"  Entorno: {'PRODUCCION' if PRODUCTION else 'TESTING (homologacion)'}")
    print(f"  Punto de venta: {PUNTO_VENTA}")
    print(f"  CUIT emisor: {CUIT}")
    print(f"  Tipo: Factura C (cod {CBTE_TIPO})")
    print(f"{'='*60}")
    print(f"  {'#':<4} {'DNI':<12} {'Monto':>12} {'Fecha':<10}")
    print(f"  {'-'*42}")

    total = 0
    for i, f in enumerate(facturas, start=1):
        doc_display = "CONS.FINAL" if f["doc_nro"] is None else str(f["doc_nro"])
        print(f"  {i:<4} {doc_display:<12} {f['imp_total']:>12.2f} {f['fecha']:<10}")
        total += f["imp_total"]

    print(f"  {'-'*42}")
    print(f"  {'TOTAL':<17} {total:>12.2f}")
    print(f"  Cantidad: {len(facturas)} factura(s)")
    print(f"{'='*60}\n")

    resp = input("Confirmar emision? [s/N]: ").strip().lower()
    return resp == "s"


def obtener_fecha_minima(afip):
    """Obtiene la fecha minima permitida para el proximo comprobante.

    AFIP no permite fecha anterior al ultimo comprobante emitido.
    Retorna el maximo entre hoy y la fecha del ultimo comprobante.
    """
    hoy = datetime.now().strftime("%Y%m%d")
    try:
        ultimo = afip.ElectronicBilling.getLastVoucher(PUNTO_VENTA, CBTE_TIPO)
        if ultimo > 0:
            info = afip.ElectronicBilling.getVoucherInfo(ultimo, PUNTO_VENTA, CBTE_TIPO)
            ultima_fecha = info["ResultGet"]["CbteFch"]
            return max(hoy, ultima_fecha)
    except Exception:
        pass
    return hoy


def emitir_factura(afip, factura, fecha_cbte):
    """Emite una factura y devuelve el resultado de AFIP.

    Usa createNextVoucher que obtiene el proximo numero de comprobante
    automaticamente, evitando conflictos de numeracion.
    """
    if factura["doc_nro"] is None:
        doc_tipo = DOC_TIPO_CONSUMIDOR_FINAL
        doc_nro = 0
    else:
        doc_tipo = DOC_TIPO
        doc_nro = factura["doc_nro"]

    data = {
        "CantReg": 1,
        "PtoVta": PUNTO_VENTA,
        "CbteTipo": CBTE_TIPO,
        "Concepto": CONCEPTO,
        "DocTipo": doc_tipo,
        "DocNro": doc_nro,
        "CbteFch": fecha_cbte,
        "ImpTotal": factura["imp_total"],
        "ImpTotConc": IMP_TOT_CONC,
        "ImpNeto": factura["imp_total"],
        "ImpOpEx": IMP_OP_EX,
        "ImpIVA": IMP_IVA,
        "ImpTrib": IMP_TRIB,
        "FchServDesde": max(factura["fecha"], fecha_cbte),
        "FchServHasta": max(factura["fecha"], fecha_cbte),
        "FchVtoPago": max(factura["fecha"], fecha_cbte),
        "MonId": MONEDA_ID,
        "MonCotiz": MONEDA_COTIZ,
        "CondicionIVAReceptorId": CONDICION_IVA_RECEPTOR,
    }

    return afip.ElectronicBilling.createNextVoucher(data)


def guardar_resultados(resultados, path_salida):
    """Guarda los resultados en un CSV."""
    campos = ["doc_nro", "imp_total", "fecha", "cbte_nro", "cae", "cae_vto", "resultado"]

    with open(path_salida, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=campos)
        writer.writeheader()
        writer.writerows(resultados)

    print(f"\nResultados guardados en: {path_salida}")


def main():
    path_csv = sys.argv[1] if len(sys.argv) > 1 else "facturas.csv"

    if not os.path.exists(path_csv):
        print(f"ERROR: No se encontro el archivo {path_csv}")
        sys.exit(1)

    facturas = leer_csv(path_csv)

    if not facturas:
        print("ERROR: El CSV esta vacio")
        sys.exit(1)

    if not mostrar_resumen(facturas):
        print("Emision cancelada.")
        sys.exit(0)

    afip_options = {"CUIT": CUIT, "access_token": ACCESS_TOKEN, "production": PRODUCTION}
    if PRODUCTION:
        if not CERT_PATH or not os.path.exists(CERT_PATH):
            print("ERROR: CERT_PATH requerido en modo produccion")
            sys.exit(1)
        if not KEY_PATH or not os.path.exists(KEY_PATH):
            print("ERROR: KEY_PATH requerido en modo produccion")
            sys.exit(1)
        afip_options["cert"] = open(CERT_PATH).read()
        afip_options["key"] = open(KEY_PATH).read()
    afip = Afip(afip_options)

    fecha_cbte = obtener_fecha_minima(afip)
    print(f"Fecha comprobante: {fecha_cbte}")

    resultados = []

    for i, factura in enumerate(facturas, start=1):
        doc_label = "CONSUMIDOR FINAL" if factura["doc_nro"] is None else f"DNI {factura['doc_nro']}"
        print(f"  [{i}/{len(facturas)}] {doc_label} - ${factura['imp_total']:.2f}...", end=" ")
        try:
            res = emitir_factura(afip, factura, fecha_cbte)
            resultados.append({
                "doc_nro": factura["doc_nro"] if factura["doc_nro"] is not None else "CONSUMIDOR FINAL",
                "imp_total": factura["imp_total"],
                "fecha": factura["fecha"],
                "cbte_nro": res["voucherNumber"],
                "cae": res["CAE"],
                "cae_vto": res["CAEFchVto"],
                "resultado": "OK",
            })
            print(f"OK (Nro: {res['voucherNumber']}, CAE: {res['CAE']})")
        except Exception as e:
            resultados.append({
                "doc_nro": factura["doc_nro"] if factura["doc_nro"] is not None else "CONSUMIDOR FINAL",
                "imp_total": factura["imp_total"],
                "fecha": factura["fecha"],
                "cbte_nro": "",
                "cae": "",
                "cae_vto": "",
                "resultado": f"ERROR: {e}",
            })
            print(f"ERROR: {e}")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    guardar_resultados(resultados, f"resultados_{timestamp}.csv")


if __name__ == "__main__":
    main()
