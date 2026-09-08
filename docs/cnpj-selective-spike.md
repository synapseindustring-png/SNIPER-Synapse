# Prova técnica — processamento seletivo de CNPJ

## Data e fonte

- execução: 05/09/2026;
- competência mais recente encontrada: `2026-08`;
- fonte: WebDAV público da Receita Federal;
- arquivo testado: `Estabelecimentos1.zip`;
- filtro: situação `02` (ativa), UF `MG`, CNAE principal prefixo `10` (fabricação de produtos alimentícios).

## Manifesto observado

Na competência testada:

- estabelecimentos: 10 ZIPs, aproximadamente 5,1 GB compactados;
- empresas: 10 ZIPs, aproximadamente 1,3 GB compactados;
- Simples: aproximadamente 288 MB;
- sócios: não necessários no MVP;
- maior parte de estabelecimentos: aproximadamente 2,1 GB compactados;
- parte usada na prova: aproximadamente 326 MB compactados e 1,08 GB descompactados logicamente.

Uma consulta nacional inédita ainda exige percorrer todas as partes de estabelecimentos, pois a Receita não oferece filtro no download. A economia ocorre em armazenamento persistente e na complementação: somente radicais candidatos seguem para empresas/Simples e PostgreSQL.

## Resultado medido

- ZIP validado integralmente antes da leitura;
- leitura direta do membro comprimido, sem extrair CSV;
- parser: `csv` da biblioteca padrão, encoding `latin1`;
- tempo da varredura: 51,43 segundos;
- memória residente máxima: 13.248 KB;
- correspondências na parte: 2.059;
- bytes adicionais de CSV gravados em disco: zero.

Exemplos encontrados incluem CNAEs `1091102`, `1020101`, `1091101`, `1099699` e `1081301` em MG.

## Falha útil observada

Uma tentativa de retomar um download parcial produziu ZIP com bytes extras e incompatível com `zipfile`, embora `unzip` tentasse compensar. Portanto:

- não confiar em resume sem verificar suporte/range e identidade do artefato;
- baixar para arquivo `.part` isolado;
- validar tamanho esperado, ETag/checksum disponível e `ZipFile.testzip()`;
- promover atomicamente para pronto somente após validação;
- reiniciar download corrompido em novo artefato, sem consumir dados parciais.

## Conclusão

A filtragem seletiva em streaming é tecnicamente viável e usa pouca memória. O gargalo é rede/descompressão, não RAM.

Arquitetura confirmada:

```text
manifesto → uma parte por vez → validar → filtrar em streaming
          → staging de candidatos → descartar ZIP → próxima parte
          → complementar somente candidatos → base curada
```

Consultas amplas e inéditas serão jobs de lote, não requests HTTP síncronos. `SourceCoverage` e cache são essenciais para evitar nova varredura quando a competência e o escopo já estiverem cobertos.

## Implementação offline

A primeira versão do leitor de produção está em `apps/sources/cnpj/establishments.py`.
Ela mantém a estratégia validada pela prova:

- lê o membro de dados diretamente de um ZIP;
- usa `csv` da biblioteca padrão e encoding `latin1`;
- exige filtro seletivo de localização ou CNAE por padrão;
- filtra situação, UF, município, CNAE principal e, opcionalmente, secundários;
- entrega resultados como iterador, sem carregar o arquivo inteiro em memória;
- registra contagens lidas, correspondentes e inválidas;
- falha explicitamente quando a quantidade de colunas diverge do layout esperado.

Os testes usam fixture pequena e ZIP criado localmente, sem rede. O job `DISCOVER_CNPJ`
já persiste os candidatos correspondentes em Company, CNAE, SourceRecord,
FieldObservation e QueryResult, com deduplicação por CNPJ e payload. Manifesto, download,
checksum, staging e complementação por Empresas/Simples pertencem às próximas fatias.
