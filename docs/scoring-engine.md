# Motor de scoring

## Garantias

O motor é determinístico, versionado e auditável. Para os mesmos dados, instante de referência e conjunto de regras, o resultado deve ser idêntico.

LLM e machine learning não participam da decisão. Toda contribuição aponta para uma regra, uma fonte e uma evidência.

## Fluxo

```text
Company + fatos atuais + sinais ativos
        ↓
Rule Set ativo e versionado
        ↓
Avaliação de condições
        ↓
Contribuições brutas
        ↓
Decay + limites por regra/grupo
        ↓
Scores 0..100
        ↓
Fórmula de prioridade
        ↓
Temperatura/classificação
        ↓
Snapshot imutável + Explain Score
```

## Condições

O MVP aceita operadores explícitos:

```text
EQ, NE, IN, NOT_IN
GT, GTE, LT, LTE, BETWEEN
EXISTS, NOT_EXISTS
CONTAINS_KEYWORD, CONTAINS_ANY, CONTAINS_ALL
REGEX
HAS_SIGNAL, HAS_CNAE_PREFIX
```

Condições compostas usam `all`, `any` e `not`, com profundidade limitada. Campos e operadores permitidos são validados por dimensão; não haverá execução de código ou SQL armazenado no banco.

Exemplo:

```json
{
  "all": [
    {"field": "registration_status", "op": "EQ", "value": "ACTIVE"},
    {"field": "primary_cnae", "op": "HAS_CNAE_PREFIX", "value": "10"}
  ]
}
```

## Indústrias

Calcular separadamente:

- ICP: estrutura relativamente estável;
- MES Fit: produção, OEE, apontamento, perdas e chão de fábrica;
- CMMS Fit: PCM, manutenção, ativos e confiabilidade;
- Pulse Fit: dados de processo, telemetria, alertas e IoT;
- Intent: mudança ou iniciativa recente.

Cada dimensão soma contribuições, aplica limites e é truncada em `0..100`. Pesos negativos são permitidos.

`Best Product Fit` é o maior entre MES, CMMS e Pulse. Empates seguem uma ordem configurável e são exibidos como empate, não ocultados.

Fórmula seed:

```text
Priority = ICP × 0,35 + Best Product Fit × 0,35 + Intent × 0,30
```

O arredondamento seed é half-up para inteiro apenas na apresentação/classificação. O valor decimal permanece no snapshot.

Temperaturas seed:

| Faixa | Temperatura |
|---:|---|
| 80–100 | HOT |
| 65–79,999... | WARM |
| 45–64,999... | WATCH |
| 0–44,999... | COLD |

Regras críticas produzem `DISQUALIFIED` independentemente do Priority. Exemplos iniciais: CNPJ inativo, atividade inequivocamente incompatível, registro inválido ou exclusão manual.

## Parceiros

Dimensões:

- Partner Fit;
- Channel Potential;
- Partner Activity;
- Conflict Penalty.

Fórmula seed:

```text
Partner Priority =
  Partner Fit × 0,45 +
  Channel Potential × 0,35 +
  Partner Activity × 0,20 -
  Conflict Penalty
```

Resultado limitado a `0..100` após a penalidade.

| Faixa | Classificação |
|---:|---|
| 80–100 | PRIORITY PARTNER |
| 65–79,999... | WARM PARTNER |
| 45–64,999... | WATCH |
| 0–44,999... | LOW PRIORITY |

Conflito crítico gera `CONFLICT` independentemente do score.

## Decay

Para um sinal com idade em dias no instante do cálculo:

| Idade | Multiplicador seed |
|---:|---:|
| 0–30 | 1,00 |
| 31–60 | 0,80 |
| 61–90 | 0,60 |
| 91–180 | 0,30 |
| acima de 180 | 0,10 ou expirado conforme a política |

```text
pontos efetivos = pontos-base × multiplicador de decay
```

CNAE, porte, segmento e localização usam política `NONE`. Vagas, notícias, expansão, contratações e projetos usam decay.

O cálculo recebe explicitamente `as_of`, evitando resultados diferentes durante testes e recálculos históricos.

## Controle de duplicidade e teto

Múltiplas fontes podem confirmar o mesmo fato sem multiplicar artificialmente o score.

Cada regra pode definir:

- `dedupe_scope`: signal, company, source ou interval;
- `max_occurrences`;
- `group_key` e `group_cap`;
- janela temporal mínima entre ocorrências equivalentes.

Exemplo: três páginas copiando a mesma vaga geram uma evidência comercial confirmada, não três contribuições integrais.

## Explain Score

Exibir para cada dimensão:

```text
+30 Vaga de PCM publicada há 5 dias
    Base: 30 | Decay: 100% | Efetivo: 30
    Fonte: página de carreiras

+16 Projeto de expansão publicado há 45 dias
    Base: 20 | Decay: 80% | Efetivo: 16
    Fonte: notícia da empresa
```

O Priority deve mostrar também a fórmula aplicada, versão das regras, melhor produto e parcelas ponderadas.

## Versionamento e publicação

Alterações são feitas em um Rule Set `DRAFT`. Publicar cria uma versão imutável e torna-a ativa. Regras já usadas em snapshots não são editadas retroativamente.

Antes da publicação, o admin verá:

- validação de pesos somando 1 quando exigido;
- condições inválidas;
- thresholds com lacunas/sobreposição;
- simulação em empresas selecionadas;
- diferenças em relação à versão ativa.

## Override

O score e temperatura calculados nunca são substituídos no snapshot. Overrides ficam em entidade separada e a UI mostra ambos.

```text
Calculated Temperature: HOT
Effective Temperature: WATCH
Override: manual, por usuário X, motivo Y
```

## Seeds iniciais

Seeds existem para viabilizar o produto, mas são hipóteses. Devem vir em migration/fixture versionada, ser editáveis no admin e conter uma descrição de negócio.

Nenhuma seed deve afirmar precisão comercial antes de validação com casos reais.

## Testes obrigatórios

- mesmas entradas produzem o mesmo snapshot;
- limites `0..100`;
- bordas de thresholds;
- decay em cada fronteira;
- exclusão e conflito crítico prevalecem;
- cap e deduplicação de contribuições;
- empate de produtos;
- versão antiga continua explicável após nova publicação;
- override sobrevive a recálculo;
- soma exibida corresponde ao valor persistido.

