# Relatório final da preparação da avaliação — 2026-10-06

Concluído após a autorização manual das cinco correções linguísticas. Nenhuma outra tradução, correção ou normalização foi aplicada nesta fase. Os candidatos, registros das 36 chamadas anteriores e o inventário da Fase 1 permanecem intactos. Este relatório substitui o relatório anterior de interrupção; a intervenção manual fica documentada na auditoria e no registro de correções.

| Item | Resultado |
|---|---|
| 1. Linhas da fonte | 36 |
| 2. Pares únicos da fonte | 36; duplicados: 0 |
| 3. Mapeamentos | 324 únicos; duplicados, ausentes e inesperados: 0 |
| 4. Português preservado | 12 |
| 5. Não português traduzido | 289 |
| 6. Campos mistos traduzidos parcialmente | 14 |
| 7. Vazios preservados | 9 |
| 8. Correções linguísticas manuais | 5 campos; apenas as substituições aprovadas |
| 9. Chamadas adicionais LLM/API nesta fase | 0; total da fase de tradução anterior: 36 |
| 10. Linhas da avaliação | 36 |
| 11. Pares únicos da avaliação | 36 |
| 12. Pares duplicados | 0 |
| 13. Pares ausentes | 0 |
| 14. Pares inesperados | 0 |
| 15. Requisitos preservados literalmente | system_purpose: 36/36; user_story: 36/36; acceptance_criteria: 36/36, inclusive comparação UTF-8 dos valores |
| 16. Vazios legítimos de padrões preservados | 9/9 |
| 17. ADRs com status Proposto | 36; títulos, contextos, decisões e consequências não vazios: 36 cada |
| 18. Validação linguística final | PASSOU: cinco resíduos autorizados removidos; nenhuma nova ocorrência problemática identificada; termos técnicos e nomes próprios convencionais preservados |
| 19. Correções aprovadas presentes | SIM; Commercial → Comercial nos quatro campos indicados; Machine Learning → aprendizado de máquina na motivação indicada |
| 20. Valores científicos originais inalterados | SIM; comparação SHA-256 com a linha de base original |
| 21. Igualdade dos conjuntos de pares | EXATA |
| 22. Chamadas de API no compilador | 0; somente biblioteca padrão |
| 23. Rerun determinístico byte a byte | PASSOU em duas novas execuções após a geração; ambos os CSVs idênticos |
| 24. SHA-256 finais | Registrados abaixo e em expert_evaluation_translation_run/final_output_hashes.json |
| 25. Arquivos criados nesta fase | 6; listados abaixo |
| 26. Arquivos preexistentes modificados nesta fase | 2 artefatos de preparação: compilador e este relatório |
| 27. Artefatos protegidos | 202 arquivos da linha de base original sem alteração; todos os demais arquivos da linha de base desta fase também inalterados |
| 28. ADRs regenerados | 0; nenhum ADR original modificado |
| 29. Prompts experimentais modificados | 0 |
| 30. Commit / push | Não realizados |

## Proveniência das cinco correções

A auditoria mantém as sete colunas originais e acrescenta somente `translation_candidate_pt`, `manual_correction_authorized`, `manual_correction_from` e `manual_correction_to`. Cada linha registra o texto científico original, o candidato da preparação e a apresentação final. Há exatamente cinco linhas com autorização manual; as outras 319 continuam idênticas aos candidatos.

`expert_evaluation_manual_corrections.csv` registra as cinco correções, o candidato, o texto final e a referência à autorização integral preservada em `expert_evaluation_translation_run/manual_authorization.txt`. As classificações linguísticas permanecem 12 + 289 + 14 + 9 = 324.

| Caso | Campo | Substituição aprovada |
|---|---|---|
| SYS03-US02 × 014 | adr_title | Commercial → Comercial |
| SYS03-US02 × 014 | adr_context | Commercial → Comercial |
| SYS03-US02 × 014 | adr_decision | Commercial → Comercial |
| SYS03-US02 × 014 | adr_consequences | Commercial → Comercial |
| SYS04-US03 × 014 | pattern_motivation | Machine Learning → aprendizado de máquina |

As 14 porções mistas foram novamente verificadas contra a fonte. O relatório individual da etapa anterior (`expert_evaluation_mixed_language_review.md`) permanece como registro dos candidatos. Para os campos mistos corrigidos de `SYS03-US02 × 014`, a auditoria final mostra ambas as versões e confirma a preservação literal de `PENDENTE DE EXECUÇÃO`.

## Reprodutibilidade

```bash
python -B research_results/compile_expert_evaluation.py
```

O compilador valida a fonte e os 324 mapeamentos antes de gravar os arquivos. Usa o inventário somente para conferir as ações linguísticas e os candidatos/correções locais para validar a proveniência. Não importa o SDK nem chama serviços externos. Rejeita alterações fora das cinco autorizadas, correções diferentes das aprovadas e mudanças nas porções portuguesas preservadas.

| Arquivo | SHA-256 |
|---|---|
| expert_evaluation_cases_pt.csv | `47a1223809b70d6b3846e75a75f14b842adedb5a9ee749de569c59a92634fb1c` |
| expert_evaluation_translation_audit.csv | `aad04703935aeb934d69c83e2d6dcd76456f9de76fc7896d7a2a502da9c26560` |

## Arquivos criados nesta fase

- `research_results/expert_evaluation_cases_pt.csv`
- `research_results/expert_evaluation_manual_corrections.csv`
- `research_results/expert_evaluation_translation_audit.csv`
- `research_results/expert_evaluation_translation_run/final_output_hashes.json`
- `research_results/expert_evaluation_translation_run/manual_authorization.txt`
- `research_results/expert_evaluation_translations_pt.csv`

## Arquivos modificados nesta fase

- `research_results/compile_expert_evaluation.py`
- `research_results/expert_evaluation_preparation_report.md`

## Material para os avaliadores

Apresentar apenas `expert_evaluation_cases_pt.csv`. O arquivo contém exatamente as 15 colunas solicitadas, sem rastreabilidade experimental, questionário ou respostas de avaliadores. Os mapeamentos, a auditoria, as correções, os candidatos e os registros de chamadas são exclusivos para pesquisadores.
