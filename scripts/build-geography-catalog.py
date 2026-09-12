#!/usr/bin/env python3
"""Build the versioned geography catalog from official IBGE and Receita files."""

import argparse
import csv
import json
import re
import unicodedata
import zipfile
from collections import defaultdict
from pathlib import Path


NAME_ALIASES = {
    "AMPARO DO SAO FRANCISCO": "AMPARO DE SAO FRANCISCO",
    "AMPARO DO SERRA": "AMPARO DA SERRA",
    "AREZ": "ARES",
    "BALNEARIO PICARRAS": "BALNEARIO DE PICARRAS",
    "BRAZOPOLIS": "BRASOPOLIS",
    "COUTO MAGALHAES": "COUTO DE MAGALHAES",
    "ELDORADO DO CARAJAS": "ELDORADO DOS CARAJAS",
    "JANUARIO CICCO": "BOA SAUDE",
    "MUQUEM DO SAO FRANCISCO": "MUQUEM DE SAO FRANCISCO",
    "PARATY": "PARATI",
    "SANTA IZABEL DO PARA": "SANTA ISABEL DO PARA",
    "SANT ANA DO LIVRAMENTO": "SANTANA DO LIVRAMENTO",
    "SANTO ANTONIO DE LEVERGER": "SANTO ANTONIO DO LEVERGER",
    "SAO LUIZ DO ANAUA": "SAO LUIZ",
    "SAO VALERIO": "SAO VALERIO DA NATIVIDADE",
    "TABOCAO": "FORTALEZA DO TABOCAO",
}

MG_COMMERCIAL_REGIONS = (
    ("MG-CENTRAL", "Central de Minas", (3101, 3113)),
    ("MG-NORTE", "Norte de Minas", (3102,)),
    ("MG-JEQUITINHONHA-MUCURI", "Vales do Jequitinhonha e Mucuri", (3103,)),
    ("MG-RIO-DOCE", "Vale do Rio Doce", (3104, 3105)),
    ("MG-MATA-CAMPOS-VERTENTES", "Zona da Mata e Campo das Vertentes", (3106, 3107)),
    ("MG-SUL-SUDOESTE", "Sul e Sudoeste de Minas", (3108, 3109)),
    ("MG-TRIANGULO-ALTO-PARANAIBA", "Triângulo Mineiro e Alto Paranaíba", (3110, 3111, 3112)),
)


def normalize_name(value):
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    return " ".join(re.sub(r"[^A-Z0-9]+", " ", value.upper()).split())


def receita_names(path):
    with zipfile.ZipFile(path) as archive:
        member = archive.namelist()[0]
        rows = csv.reader(
            (line.decode("latin1") for line in archive.open(member)), delimiter=";"
        )
        return defaultdict(list, {
            name: values
            for name, values in _group_rows(rows).items()
        })


def _group_rows(rows):
    grouped = defaultdict(list)
    for code, name, *_ in rows:
        grouped[normalize_name(name)].append(code)
    return grouped


def build(ibge_municipalities_path, receita_zip_path):
    municipalities = json.loads(Path(ibge_municipalities_path).read_text())
    receita_by_name = receita_names(receita_zip_path)
    official_regions = {}
    output_municipalities = []
    missing = []

    for item in municipalities:
        immediate = item["regiao-imediata"]
        intermediate = immediate["regiao-intermediaria"]
        state = intermediate["UF"]
        normalized = normalize_name(item["nome"])
        receita_name = NAME_ALIASES.get(normalized, normalized)
        matches = receita_by_name.get(receita_name, [])
        if not matches:
            missing.append(item["nome"])
            continue
        # Duplicate city names exist in Brazil. Their Receita codes are all retained;
        # the state condition applied with every search prevents cross-state matches.
        municipality = {
            "ibge_code": str(item["id"]),
            "receita_codes": sorted(set(matches)),
            "name": item["nome"],
            "state": state["sigla"],
            "immediate_code": str(immediate["id"]),
            "immediate_name": immediate["nome"],
            "intermediate_code": str(intermediate["id"]),
            "intermediate_name": intermediate["nome"],
        }
        output_municipalities.append(municipality)
        region = official_regions.setdefault(
            intermediate["id"],
            {
                "code": f"IBGE-I-{intermediate['id']}",
                "name": intermediate["nome"],
                "state": state["sigla"],
                "state_name": state["nome"],
                "kind": "IBGE_INTERMEDIATE",
                "source_region_codes": [str(intermediate["id"])],
                "municipality_ibge_codes": [],
            },
        )
        region["municipality_ibge_codes"].append(str(item["id"]))

    if missing:
        raise RuntimeError(f"Municípios sem correspondência na Receita: {missing}")

    regions = list(official_regions.values())
    for code, name, source_codes in MG_COMMERCIAL_REGIONS:
        member_codes = []
        for source_code in source_codes:
            member_codes.extend(official_regions[source_code]["municipality_ibge_codes"])
        regions.append(
            {
                "code": code,
                "name": name,
                "state": "MG",
                "state_name": "Minas Gerais",
                "kind": "COMMERCIAL",
                "source_region_codes": [str(value) for value in source_codes],
                "municipality_ibge_codes": sorted(member_codes),
            }
        )

    return {
        "source_version": "IBGE-2017/Receita-2026-08",
        "municipalities": sorted(output_municipalities, key=lambda row: row["ibge_code"]),
        "regions": sorted(regions, key=lambda row: (row["state"], row["kind"], row["name"])),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ibge-municipalities", required=True)
    parser.add_argument("--receita-municipalities", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    catalog = build(args.ibge_municipalities, args.receita_municipalities)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(catalog, ensure_ascii=False, separators=(",", ":")))
    print(f"{len(catalog['municipalities'])} municípios e {len(catalog['regions'])} regiões")


if __name__ == "__main__":
    main()
