# ADR4AI RQ1: response-conditioned support evaluation

## Scope and source validation

This is a descriptive analysis of Claude's recorded support for original GPT classifications, conditioned on the GPT decision and rationale. Support for a decision is distinct from architectural correctness and from human expert evaluation. No blind Claude results or architects' Q5 scores enter this analysis. No new model calls or expert adjudications were made.

The frozen consolidated records pass exact source reconstruction, the unchanged original support JSON/schema and case-reference validator, and source/manifest/correction hash checks: **840 unique pairs**, the full Cartesian product of 12 stories and 70 patterns across four systems. GPT marginal counts are **36 applicable, 31 not_applicable, 773 insufficient_information**. Scientific protocol is `adr4ai-rq1-response-conditioned-support-v1.1` (v1.1); operational amendment is `adr4ai-rq1-support-validation-continuation-op1` (op1). Source identifiers and hashes are recorded in `analysis_provenance.json` and `validation.json`.

There are **839 originally API-validated judgments and one technically corrected analytical record**, SYS02-US01 × P051. The official records still contain 839 validated judgments. The existing approved correction replaces only `SYS02-US01-US01` with `SYS02-US01` in the earliest failed response's evidence references. Original verdict (`supported`), rationale, and identified gaps are unchanged; the second failed response and its different rationale remain preserved. All 839 original judgments match their preserved source records exactly. This analysis does not modify the correction or relabel it as originally validated.

| Subset | N | supported | partially_supported | unsupported |
| --- | --- | --- | --- | --- |
| official_api_validated | 839 | 395 | 443 | 1 |
| technically_corrected_analytical | 1 | 1 | 0 | 0 |

Excluding the correction yields 395 supported, 443 partially_supported, and one unsupported judgment (839). The correction affects only the not_applicable row (29/1/0 becomes 30/1/0), and none of the 36 applicable decisions.

## Descriptive support matrix

Percentages use the original GPT category as denominator; totals are counts of pair-level decisions, not distinct catalog patterns.

| GPT classification | N | Supported | Partially supported | Unsupported |
| --- | --- | --- | --- | --- |
| applicable | 36 | 21 (58.33%) | 15 (41.67%) | 0 (0.00%) |
| not_applicable | 31 | 30 (96.77%) | 1 (3.23%) | 0 (0.00%) |
| insufficient_information | 773 | 345 (44.63%) | 427 (55.24%) | 1 (0.13%) |

Overall: **396 supported (47.14%), 443 partially_supported (52.74%), one unsupported (0.12%)**. These are support-verdict frequencies, not agreement, accuracy, precision, recall, or evidence of model superiority. The highly unequal GPT category sizes mean the overall distribution mostly reflects insufficient_information decisions.

### By system (all classifications)

| system | N | supported | partially_supported | unsupported |
| --- | --- | --- | --- | --- |
| System_01 | 210 | 88 (41.90%) | 122 (58.10%) | 0 (0.00%) |
| System_02 | 210 | 102 (48.57%) | 108 (51.43%) | 0 (0.00%) |
| System_03 | 210 | 95 (45.24%) | 115 (54.76%) | 0 (0.00%) |
| System_04 | 210 | 111 (52.86%) | 98 (46.67%) | 1 (0.48%) |

### By user story (all classifications)

| user_story_id | N | supported | partially_supported | unsupported |
| --- | --- | --- | --- | --- |
| SYS01-US01 | 70 | 29 (41.43%) | 41 (58.57%) | 0 (0.00%) |
| SYS01-US02 | 70 | 37 (52.86%) | 33 (47.14%) | 0 (0.00%) |
| SYS01-US03 | 70 | 22 (31.43%) | 48 (68.57%) | 0 (0.00%) |
| SYS02-US01 | 70 | 37 (52.86%) | 33 (47.14%) | 0 (0.00%) |
| SYS02-US02 | 70 | 37 (52.86%) | 33 (47.14%) | 0 (0.00%) |
| SYS02-US03 | 70 | 28 (40.00%) | 42 (60.00%) | 0 (0.00%) |
| SYS03-US01 | 70 | 48 (68.57%) | 22 (31.43%) | 0 (0.00%) |
| SYS03-US02 | 70 | 23 (32.86%) | 47 (67.14%) | 0 (0.00%) |
| SYS03-US03 | 70 | 24 (34.29%) | 46 (65.71%) | 0 (0.00%) |
| SYS04-US01 | 70 | 43 (61.43%) | 26 (37.14%) | 1 (1.43%) |
| SYS04-US02 | 70 | 21 (30.00%) | 49 (70.00%) | 0 (0.00%) |
| SYS04-US03 | 70 | 47 (67.14%) | 23 (32.86%) | 0 (0.00%) |

`by_system.csv` and `by_story.csv` additionally cross each group with all three GPT categories, including zero-denominator categories (blank percentage). Counts and six-decimal percentages are recalculated directly; display percentages are rounded to two decimals.

## The 36 GPT-applicable decisions used for ADR generation

Of the 36 decisions, **21 (58.33%) are supported, 15 (41.67%) partially_supported, and none unsupported**. All 36 are original validated records. These are 36 story–pattern selections; the same catalog pattern can recur across stories. This evaluates the evidential support of the selections, not the quality or correctness of the generated ADRs.

| system | N | supported | partially_supported | unsupported |
| --- | --- | --- | --- | --- |
| System_01 | 7 | 4 (57.14%) | 3 (42.86%) | 0 (0.00%) |
| System_02 | 12 | 5 (41.67%) | 7 (58.33%) | 0 (0.00%) |
| System_03 | 8 | 6 (75.00%) | 2 (25.00%) | 0 (0.00%) |
| System_04 | 9 | 6 (66.67%) | 3 (33.33%) | 0 (0.00%) |

The complete case table `applicable_decisions.csv` retains every original rationale, evidence-reference array and identified-gap array verbatim, with origin and source identifiers. CSV array cells contain JSON; pattern identifiers are zero-padded strings.

### Transparent qualitative procedure

All 15 applicable partially_supported judgments were read individually. `applicable_partial_coding.json` contains assistant-authored, post-hoc, multi-label annotations, full verbatim gap quotes, and case-specific notes. `codebook.json` defines the codes. The analysis is descriptive coding of the judge's explanations, not an independent architecture assessment; there is one coder, no preregistration and no inter-coder reliability estimate. Code frequencies overlap and must not be summed as distinct decisions. Exact quote and case coverage checks run offline. No recorded verdict is changed.

| Code | Interpretation | Cases / 15 | Representative case |
| --- | --- | --- | --- |
| A1 | Requirement-to-pattern-mechanism inference | 12 | SYS01-US03 × P001 |
| A2 | Task variety versus composable pipeline | 3 | SYS02-US01 × P002 |
| A3 | Related concern or scope is not identical intent | 7 | SYS01-US03 × P001 |
| A4 | ML or domain-framing transfer | 4 | SYS01-US03 × P001 |
| A5 | Rationale or criterion coverage | 4 | SYS01-US03 × P013 |
| A6 | Dependency versus interaction contract | 2 | SYS03-US03 × P050 |
| A7 | Alternative-design or necessity argument alongside a specific concern | 7 | SYS01-US03 × P060 |

| Case | Codes | Post-hoc interpretation (not a new verdict) |
| --- | --- | --- |
| SYS01-US03 × P001 | A1, A3, A4 | The judge distinguishes traceability from a rule-based output safeguard. This is a specific claimed evidence-to-intent gap; the annotation does not establish that an explicit mechanism is necessary for applicability. |
| SYS01-US03 × P013 | A1, A3, A5 | Source transparency is linked to a generic motivation while adaptive interface/orchestration needs are unshown in the judge's account. Treat the specific mapping concern separately from insisting on the complete implementation. |
| SYS01-US03 × P060 | A1, A3, A7 | The judge distinguishes a content-scope constraint from prediction-serving controls, but also invokes other ways to satisfy it. Alternative solutions alone are not a justification defect. |
| SYS02-US01 × P002 | A1, A2, A7 | The judge questions the jump from document operations to independent filters and intermediate data flow. A cohesive template routine is an alternative, not by itself evidence against a defensible pipeline interpretation. |
| SYS02-US02 × P001 | A1, A4, A7 | The judge identifies unstated ML/gating and safety assumptions beyond a context-preservation constraint. A preservation check being only one option does not alone weaken applicability. |
| SYS02-US02 × P002 | A1, A2, A5 | The specific issue is treating user-selected tasks as an ordered composable pipeline. Criticism of omitted criteria does not establish a requirement to cite every criterion. |
| SYS02-US02 × P060 | A1, A3 | The judge distinguishes a selected transformation mode and preservation goal from anomaly/edge-case serving controls. This is an intent-mapping concern rather than generic uncertainty. |
| SYS02-US02 × P064 | A1, A3, A5 | Functional on-demand editing is distinguished from a production-workflow shift toward enrichment cycles. The judge's references to all enablers should not be read as a universal requirement to specify the whole architecture. |
| SYS02-US02 × P070 | A1, A7 | The judge questions inference of multiple models from task variation, while also asking why one model could not suffice. Multiple models needing not be unique/best is distinct from evidence for condition-based selection. |
| SYS02-US03 × P002 | A1, A2, A7 | The judge distinguishes a list of saving-time operations from modular filters. A one-routine alternative does not independently establish a support deficiency. |
| SYS03-US02 × P001 | A1, A4 | The judge calls uncertainty, deterministic safeguards, and security framing unstated. This is a concrete claimed inference gap, not an independent finding that the concern is absent. |
| SYS03-US03 × P050 | A6, A7 | The judge separates conditional dependency from synchronous blocking and invokes asynchronous alternatives. Compare its supported SYS03-US02 × 050 wording; the recorded evidential thresholds may differ. |
| SYS04-US02 × P028 | A3, A4 | The judge distinguishes a product's integration-test feature from ML release-gating tests and asks for domain transfer to be justified. Technological context alone should not negate shared architectural intent. |
| SYS04-US03 × P001 | A1, A3 | The judge distinguishes environment isolation from a rule-based decision layer around predictions. Both share protective intent; the annotation does not decide whether that shared intent is sufficient. |
| SYS04-US03 × P003 | A5, A6, A7 | The judge asks for client-initiated/concurrent access beyond shared variables and model connections. Sequential evaluation is an alternative; concurrency or a unique topology is not automatically required by the support rubric. |

The recurring substantive claim is that a functional goal, quality constraint, or adjacent concern does not sufficiently establish the particular pattern mechanism. Pipes and Filters cases distinguish task variety from composable stages; safeguard/control cases distinguish output correctness, provenance or isolation from rule-based gating. Other cases question translation from ML-specific language, workflow transformation, interaction contracts, or omitted evidence mappings. These are **claimed evidential concerns recorded by the judge**, not verified architectural defects. Requiring an explicit implementation of every pattern mechanism, rather than positive evidence of its architectural need, would exceed an applicability assessment; the recorded language sometimes approaches that stricter standard.

Seven of the 15 rationales also invoke alternative designs or whether a mechanism is necessary (A7). A single routine, a single model, or asynchronous interaction may be viable alternatives without undermining another defensible selection. These seven also contain specific claimed mapping limitations; they are not coded as general uncertainty alone. Likewise, domain transfer, missing literal terminology, or failure to cite every criterion does not by itself invalidate applicability. None of these interpretations reassigns the judge's verdict.

### Representative cases

- **Supported, SYS01-US01 × P001:** the recorded rationale ties document-grounded answering and refusal outside the source context to safeguard intent. This is an example of the judge accepting a positive requirement-to-intent link.
- **Supported, SYS03-US02 × P050:** downstream status change and scheduling depend on the AI ownership confirmation. The judge accepts this as a defensible blocker motivation despite no explicit waiting requirement and acknowledges alternatives.
- **Partially supported, SYS03-US03 × P050:** conditional closure after a negative ownership result is accepted as a meaningful basis, but missing explicit synchronous waiting and the availability of asynchronous designs limit support. Juxtaposition with the preceding case illustrates a potentially variable evidential threshold, not proof that either judgment is incorrect.
- **Partially supported, SYS02-US02 × P070:** the judge accepts task/input variation as a basis but questions the inference to multiple selectable models. The reference to a single-model alternative must be distinguished from the more specific claimed requirement-to-mechanism gap.
- **Partially supported, SYS04-US02 × P028:** the judge accepts integration-testing intent but questions the transfer from ML release testing to simulator testability. This is a recorded scope/domain distinction, not a finding that patterns cannot transfer across domains.
- **Supported, SYS04-US03 × P043:** the recorded rationale accepts comparing interchangeable models against the same simulation scenario as support for Strategy intent.

Full unedited texts for these examples and the remaining-classification examples are exported in `representative_cases.csv`.

## The 31 not_applicable decisions

**30 (96.77%) are supported; one (3.23%) is partially_supported; none unsupported.** The only partial case, SYS04-US03 × P034 (Dogfooding), contrasts simulation-based evaluation with internal-user feedback, but acknowledges plausible internal users and overlap in low-risk testing. Its rationale explicitly asks whether absent feedback/toggling is evidence of mismatch or merely missing positive evidence. This is a recorded qualification of non-applicability, not a proposed reversal. All 31 texts and origins are in `not_applicable_decisions.csv`; P051 is separately labeled corrected.

## The 773 insufficient_information decisions

**345 (44.63%) are supported; 427 (55.24%) partially_supported; one (0.13%) unsupported.** The 428 non-supported judgments are exported with full original texts and auditable text flags in `insufficient_information_review.csv`. Unlike the 15-case close reading, this larger subset receives a complete deterministic text-rule pass plus selected close readings. This does not claim exhaustive semantic adjudication of all 428 cases.

### Recurring recorded explanations and rubric-sensitive language

Rules in `codebook.json` search case-insensitively within each rationale or individual gap, without normalization. Each case counts at most once per signal; labels overlap. `text_signal_evidence.csv` preserves the complete originating field for every match. `text_signal_summary.csv` also separates partially_supported and unsupported counts. These are lexical observations, not validated rates of protocol violation, and rule non-matches do not establish absence of a concern.

| Signal | Rule-based observation | Cases / 428 | % of 428 |
| --- | --- | --- | --- |
| I1 | Uncertainty/non-applicability boundary mentioned | 418 | 97.66% |
| I2 | Boundary criticism in identified gaps | 372 | 86.92% |
| I3 | Absence of contradiction or incompatibility acknowledged | 204 | 47.66% |
| I4 | Reference omission criticized in identified gaps | 26 | 6.07% |
| I5 | Incomplete rationale engagement criticized | 391 | 91.36% |
| I6 | Alternative or non-unique interpretation mentioned | 67 | 15.65% |

The intersection of a boundary criticism in gaps (I2) and acknowledged absence of incompatibility in the rationale (I3) contains **179 cases**. This identifies candidates for scrutiny, not a count of demonstrated conflations. The dominant recorded explanation questions why an absent pattern concern justifies uncertainty rather than contextual mismatch, often coupled with requests to engage more explicitly with particular criteria. Material evidence overlooked by a rationale can be a legitimate support limitation; requiring missing architectural details or rejecting uncertainty simply because the story is functionally specific can conflict with the v1.1 clarification. Recorded verdicts alone cannot settle that distinction.

Selected close readings illustrate both possibilities:

- **SYS01-US01 × P002, partially_supported:** the rationale accepts that a pipeline could implement retrieval/answering but that possibility does not establish a pipeline requirement; it also acknowledges no incompatibility, yet questions the uncertainty-versus-mismatch explanation. This raises a rubric-sensitive boundary issue rather than establishing non-applicability.
- **SYS01-US01 × P003, partially_supported:** the judge identifies a potential requester/provider interpretation and criticizes incomplete consideration of that evidence, while acknowledging missing explicit multiple-client/network details. This is a more specific claimed evidence-engagement limitation; it should not be grouped automatically with criticism of missing detail alone.
- **SYS01-US01 × P044; SYS04-US03 × P063 and P069, partially_supported:** recorded gaps criticize absent requirement references while expressly acknowledging that omission is permitted. These examples warrant caution about whether a concrete material reasoning limitation, rather than the allowed empty array itself, underlies the verdict. They are not silently excluded or rescored. The I4 count is a reproducible lexical flag, not an estimate of confirmed invalid judgments.
- **SYS04-US01 × P026 (CI/CD), the sole unsupported case:** the judge treats the functionally specified simulation context and lack of build/test/release requirements as a relevant contextual mismatch and proposes not_applicable. Its rationale simultaneously states: “Absence of positive evidence alone does not establish non-applicability, so the more defensible result is not_applicable rather than insufficient_information.” This contains an apparent tension between the stated principle and proposed replacement. The protocol asks for support assessment, not replacement classification. The judgment remains recorded as unsupported; this analysis does not establish GPT error or substitute a verdict.

An absence of architectural information may be precisely what supports insufficient_information; absence of contradiction is also not positive applicability evidence. Neither direction can be resolved by absence alone. These cautions are particularly material because 773 of 840 original classifications occupy this category.

## Methodological limitations

1. **Response conditioning:** the judge sees the original GPT classification and rationale. Support frequencies are not independent classification replication and may reflect anchoring or the presentation of justification.
2. **No complete human ground truth:** support for a rationale does not establish architectural correctness, ADR quality or human endorsement. No error, false-positive, accuracy or superiority claims are warranted. Human Q5 integration is deferred.
3. **Unequal categories and dependent observations:** stories share systems and patterns recur. The 840 pairs are a finite study corpus, not 840 independent random observations; no inferential significance tests or confidence intervals are claimed. Applicable decisions form a selected 36-case subset.
4. **Judge/rubric behavior:** machine-valid references and JSON do not establish semantic adherence. Some rationales invoke uniqueness, domain literalism, permitted reference omission, or uncertainty-versus-mismatch tensions. Text flags identify language, not independently confirmed reasoning failures.
5. **Qualitative subjectivity:** codes are post-hoc single-assistant interpretations of recorded text, not new expert assessments. Multi-label frequencies depend on explicit code definitions and regex vocabulary; they do not quantify causal reasons or objective defects.
6. **One analytical correction:** the 840th record is a documented reference-only correction of an originally invalid response, not an original API-validated judgment. Its inclusion adds one supported not_applicable decision and changes no applicable-case result. Both failed attempts remain preserved; source selection was earliest attempt rather than outcome selection.
7. **Single execution:** these data describe one configured judge run, not variability across runs, prompts or model families. No blind-run results or RAG baseline are included.

## Reproduction and files

From the repository root, without credentials or network access:

```bash
python -B research_results/llm_judge_support_rq1/analysis/analyze.py
python -B -m unittest discover -s research_results/llm_judge_support_rq1/analysis -p 'test_analysis.py' -v
```

The runner reads and validates frozen source records, emits deterministic reports only into this `analysis/` directory, and checks source hashes again after computation. Existing generated files must be byte-identical on rerun; it refuses differing overwrites. No scientific or experimental artifacts are edited. `analysis_provenance.json` records source, code, codebook, annotation and output hashes; `validation.json` records coverage and validation status.

Outputs: `support_matrix.csv`, `by_system.csv`, `by_story.csv`, `applicable_decisions.csv`, `not_applicable_decisions.csv`, `insufficient_information_review.csv`, `evidence_limitations.csv`, `text_signal_summary.csv`, `text_signal_evidence.csv`, `representative_cases.csv`, `statistics.json`, this `report.md`, validation and provenance JSON. Input coding artifacts are `codebook.json` and `applicable_partial_coding.json`; reproducible code/tests are `analyze.py` and `test_analysis.py`.
