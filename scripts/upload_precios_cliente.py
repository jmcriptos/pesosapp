#!/usr/bin/env python3
"""
Sube CSVs de precios por cliente al endpoint de carga masiva.

Modo recomendado para tu caso:
- Un archivo por cliente en una carpeta
- tipo_carga=precios_especificos
- Si el CSV no trae 'codigo_cliente', se infiere desde el nombre del archivo

Ejemplo:
python scripts/upload_precios_cliente.py \
  --base-url https://pesosapp-caa46963237c.herokuapp.com \
  --username jdasilva \
  --password '***' \
  --folder /ruta/a/csvs \
  --client-mode filename \
  --filename-regex '^(?P<codigo_cliente>\\d+)'
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import re
import shutil
import sys
from pathlib import Path
from typing import Dict, List, Tuple

import requests


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Carga masiva de precios específicos por cliente (CSVs por carpeta)."
    )
    parser.add_argument("--base-url", required=True, help="URL base de la app")
    parser.add_argument("--username", required=True, help="Usuario de login")
    parser.add_argument("--password", required=True, help="Password de login")
    parser.add_argument("--folder", required=True, help="Carpeta con archivos CSV")
    parser.add_argument(
        "--pattern",
        default="*.csv",
        help="Patrón de archivos dentro de la carpeta (default: *.csv)",
    )
    parser.add_argument(
        "--client-mode",
        choices=["column", "filename", "map"],
        default="filename",
        help=(
            "Cómo obtener codigo_cliente: "
            "column=del CSV, filename=desde nombre de archivo, map=archivo de mapeo"
        ),
    )
    parser.add_argument(
        "--filename-regex",
        default=r"^(?P<codigo_cliente>\d+)",
        help=(
            "Regex para extraer codigo_cliente desde el nombre del archivo "
            "(debe tener grupo nombrado 'codigo_cliente')."
        ),
    )
    parser.add_argument(
        "--client-map",
        help="CSV de mapeo para client-mode=map con columnas: archivo,codigo_cliente",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=60,
        help="Timeout HTTP en segundos (default: 60)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Solo valida y muestra plan de carga; no sube nada.",
    )
    parser.add_argument(
        "--processed-dir",
        help="Mover archivos exitosos a esta carpeta (opcional).",
    )
    parser.add_argument(
        "--failed-dir",
        help="Mover archivos con error a esta carpeta (opcional).",
    )
    return parser.parse_args()


def extract_csrf_token(html: str) -> str:
    patterns = [
        r'<meta name="csrf-token" content="([^"]+)">',
        r'<input type="hidden" name="csrf_token" value="([^"]+)"',
    ]
    for pattern in patterns:
        match = re.search(pattern, html)
        if match:
            return match.group(1)
    raise RuntimeError("No se encontró csrf_token en la respuesta HTML")


def login(session: requests.Session, base_url: str, username: str, password: str, timeout: int) -> None:
    login_url = f"{base_url.rstrip('/')}/login"
    resp = session.get(login_url, timeout=timeout)
    resp.raise_for_status()
    csrf = extract_csrf_token(resp.text)

    payload = {
        "username": username,
        "password": password,
        "csrf_token": csrf,
        "next": "",
    }
    post = session.post(login_url, data=payload, allow_redirects=False, timeout=timeout)

    if post.status_code not in (302, 303):
        snippet = post.text[:400].replace("\n", " ")
        raise RuntimeError(
            f"Login no exitoso. status={post.status_code}. Respuesta: {snippet}"
        )


def get_upload_csrf(session: requests.Session, base_url: str, timeout: int) -> str:
    url = f"{base_url.rstrip('/')}/precios/carga-masiva"
    resp = session.get(url, timeout=timeout, allow_redirects=True)
    if resp.status_code != 200:
        raise RuntimeError(f"No se pudo abrir carga-masiva. status={resp.status_code}")
    return extract_csrf_token(resp.text)


def load_client_map(path: str | None) -> Dict[str, str]:
    mapping: Dict[str, str] = {}
    if not path:
        return mapping

    map_file = Path(path)
    if not map_file.exists():
        raise RuntimeError(f"No existe archivo de mapeo: {map_file}")

    with map_file.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        required = {"archivo", "codigo_cliente"}
        if not required.issubset(set(reader.fieldnames or [])):
            raise RuntimeError("El client-map debe tener columnas: archivo,codigo_cliente")
        for row in reader:
            archivo = (row.get("archivo") or "").strip().lower()
            codigo = (row.get("codigo_cliente") or "").strip()
            if archivo and codigo:
                mapping[archivo] = codigo
    return mapping


def infer_client_code(path: Path, mode: str, filename_regex: str, mapping: Dict[str, str]) -> str:
    if mode == "filename":
        regex = re.compile(filename_regex)
        match = regex.search(path.stem)
        if not match:
            raise RuntimeError(
                f"No se pudo inferir codigo_cliente desde nombre '{path.name}' "
                f"con regex '{filename_regex}'"
            )
        code = (match.groupdict().get("codigo_cliente") or "").strip()
        if not code:
            raise RuntimeError(
                f"El regex no contiene grupo valido 'codigo_cliente' para '{path.name}'"
            )
        return code

    if mode == "map":
        key = path.name.lower()
        code = mapping.get(key, "").strip()
        if not code:
            raise RuntimeError(f"No existe mapeo codigo_cliente para archivo '{path.name}'")
        return code

    return ""


def validate_and_normalize_csv(
    file_path: Path,
    client_mode: str,
    inferred_client_code: str,
) -> Tuple[str, int]:
    with file_path.open("r", encoding="utf-8-sig", newline="") as fh:
        content = fh.read()

    reader = csv.DictReader(io.StringIO(content))
    fieldnames = list(reader.fieldnames or [])
    if not fieldnames:
        raise RuntimeError("CSV vacío o sin encabezados")

    rows: List[Dict[str, str]] = list(reader)
    if not rows:
        raise RuntimeError("CSV sin filas de datos")

    required_base = {"codigo_producto", "precio_base"}
    if not required_base.issubset(set(fieldnames)):
        missing = ", ".join(sorted(required_base - set(fieldnames)))
        raise RuntimeError(f"Faltan columnas requeridas: {missing}")

    need_client_column = "codigo_cliente" not in fieldnames
    if client_mode == "column" and need_client_column:
        raise RuntimeError(
            "client-mode=column requiere columna 'codigo_cliente' en cada fila"
        )
    if client_mode in ("filename", "map") and need_client_column:
        fieldnames = ["codigo_cliente"] + fieldnames

    validated_rows: List[Dict[str, str]] = []
    for index, row in enumerate(rows, start=2):
        normalized = {k: (row.get(k) or "").strip() for k in row.keys()}

        if need_client_column and client_mode in ("filename", "map"):
            normalized["codigo_cliente"] = inferred_client_code

        client_code = (normalized.get("codigo_cliente") or "").strip()
        product_code = (normalized.get("codigo_producto") or "").strip()
        price_raw = (normalized.get("precio_base") or "").strip()
        mj_raw = (normalized.get("margen_jomar") or "").strip()
        mr_raw = (normalized.get("margen_retail") or "").strip()

        if not client_code:
            raise RuntimeError(f"Fila {index}: codigo_cliente vacío")
        if not product_code:
            raise RuntimeError(f"Fila {index}: codigo_producto vacío")
        if not price_raw:
            raise RuntimeError(f"Fila {index}: precio_base vacío")

        try:
            price = float(price_raw)
        except ValueError as exc:
            raise RuntimeError(f"Fila {index}: precio_base inválido '{price_raw}'") from exc
        if price <= 0:
            raise RuntimeError(f"Fila {index}: precio_base debe ser > 0 (valor={price_raw})")

        if mj_raw:
            try:
                mj = float(mj_raw)
            except ValueError as exc:
                raise RuntimeError(f"Fila {index}: margen_jomar inválido '{mj_raw}'") from exc
            if mj <= 0:
                raise RuntimeError(f"Fila {index}: margen_jomar debe ser > 0 (valor={mj_raw})")

        if mr_raw:
            try:
                mr = float(mr_raw)
            except ValueError as exc:
                raise RuntimeError(f"Fila {index}: margen_retail inválido '{mr_raw}'") from exc
            if mr <= 0:
                raise RuntimeError(f"Fila {index}: margen_retail debe ser > 0 (valor={mr_raw})")

        validated_rows.append(normalized)

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    for row in validated_rows:
        out_row = {key: row.get(key, "") for key in fieldnames}
        writer.writerow(out_row)

    return output.getvalue(), len(validated_rows)


def move_file(src: Path, dst_dir: str | None) -> None:
    if not dst_dir:
        return
    target_dir = Path(dst_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(target_dir / src.name))


def main() -> int:
    args = parse_args()
    base_url = args.base_url.rstrip("/")
    folder = Path(args.folder)
    if not folder.exists() or not folder.is_dir():
        print(f"ERROR: Carpeta no válida: {folder}", file=sys.stderr)
        return 2

    files = sorted(folder.glob(args.pattern))
    if not files:
        print("No se encontraron archivos para procesar.")
        return 0

    client_map = load_client_map(args.client_map)

    session = requests.Session()
    try:
        login(session, base_url, args.username, args.password, args.timeout)
        upload_csrf = get_upload_csrf(session, base_url, args.timeout)
    except Exception as exc:
        print(f"ERROR login/csrf: {exc}", file=sys.stderr)
        return 2

    ok = 0
    failed = 0
    total_rows = 0
    process_url = f"{base_url}/precios/procesar-csv"

    for csv_file in files:
        try:
            inferred_client = infer_client_code(
                csv_file, args.client_mode, args.filename_regex, client_map
            )
            normalized_csv, rows = validate_and_normalize_csv(
                csv_file, args.client_mode, inferred_client
            )
            total_rows += rows

            if args.dry_run:
                print(f"[DRY-RUN] OK {csv_file.name}: {rows} filas")
                ok += 1
                continue

            files_payload = {
                "archivo_csv": (
                    csv_file.name,
                    normalized_csv.encode("utf-8"),
                    "text/csv",
                )
            }
            data_payload = {
                "tipo_carga": "precios_especificos",
                "csrf_token": upload_csrf,
            }

            resp = session.post(
                process_url,
                data=data_payload,
                files=files_payload,
                timeout=args.timeout,
            )
            payload = {}
            try:
                payload = resp.json()
            except json.JSONDecodeError:
                pass

            if resp.status_code != 200 or not payload.get("success"):
                msg = payload.get("error") or payload.get("mensaje") or resp.text[:300]
                raise RuntimeError(f"HTTP {resp.status_code}: {msg}")

            errores = payload.get("resultados", {}).get("errores", 0)
            procesados = payload.get("resultados", {}).get("procesados", 0)
            print(
                f"[OK] {csv_file.name}: procesados={procesados} errores={errores} "
                f"mensaje='{payload.get('mensaje', '')}'"
            )
            ok += 1
            move_file(csv_file, args.processed_dir)

        except Exception as exc:
            failed += 1
            print(f"[ERROR] {csv_file.name}: {exc}", file=sys.stderr)
            move_file(csv_file, args.failed_dir)

    print(
        f"\nResumen: archivos_ok={ok} archivos_error={failed} "
        f"total_archivos={len(files)} total_filas={total_rows}"
    )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
