# ADR4AI expert-evaluation questionnaire

`create_expert_evaluation_form.gs` is a standalone Google Apps Script that creates **Avaliação de Decisões Arquiteturais — ADR4AI** when the researcher deliberately executes it in their own Google account. The generated questionnaire evaluates the ADR first (Q1–Q4), followed by pattern applicability (Q5).

The only content source is `research_results/expert_evaluation_cases_pt.csv`. All 36 finalized cases are embedded directly in the script as JavaScript data, with every field value preserved exactly. No CSV upload, external dependency, translation service, or OpenAI API is needed. No scientific or evaluation artifact is modified.

## Manual creation

1. Open [Google Apps Script](https://script.google.com/) and create a new project.
2. Replace the default code with the **entire** contents of `create_expert_evaluation_form.gs`, including the embedded cases. Use the Apps Script V8 runtime.
3. Review the script and its questionnaire content.
4. Change `ALLOW_FORM_CREATION` from `false` to `true`.
5. Select and run `createExpertEvaluationForm()`.
6. Authorize the Google permissions requested for Forms, the response spreadsheet, and script execution. No advanced service needs enabling.
7. Read the execution log: **Form edit URL**, **Respondent URL**, and **Response spreadsheet URL** identify the generated artifacts. The spreadsheet is named **ADR4AI - Avaliação de Especialistas - Respostas** and is linked as the form's response destination.
8. Reset `ALLOW_FORM_CREATION` to `false`. Review the form through its edit URL, check responder access as described below, and preview all four system routes before distributing the respondent URL.

Creating the form also publishes it and enables responses at the end of successful construction. It is created unpublished while content and the spreadsheet are being prepared. This repository task did **not** authenticate with Google, create a form or sheet, or call a Google API.

## Organization and branching

The initial page contains **Perfil do Avaliador**, the three required profile questions, and the required single-choice system selection. Each evaluator should choose **only the system they know or have experience with**.

| Selection | Cases presented | Required ADR ratings | Optional comments | Next page |
|---|---:|---:|---:|---|
| SYS01 | 7 | 35 | 7 | Finalização |
| SYS02 | 12 | 60 | 12 | Finalização |
| SYS03 | 8 | 40 | 8 | Finalização |
| SYS04 | 9 | 45 | 9 | Finalização |

Each system occupies one page. Within it, cases are grouped by user story, retaining their source order. Purpose, user story, and acceptance criteria appear once per story. Each case displays **Caso: user_story_id / pattern_id**, followed by the pattern and the ADR in explanatory text. Legitimately empty pattern fields are omitted from the display; their embedded values remain empty. There are no invented replacements for missing content.

For every ADR, Q1–Q5 use the exact requested wording and order, a required 1–5 scale labeled **Discordo totalmente** and **Concordo totalmente**, and a following optional paragraph comment. Question titles start with `[user_story_id|pattern_id|Q1]` through `Q5`, or `[user_story_id|pattern_id|COMMENT]`, so response columns map to exact cases. Questions from unselected systems are skipped, including their required questions. Their response columns will therefore be blank; those blanks represent routing, not missing ratings for the selected system.

All four branches converge on **Finalização** and then submission. They never continue into another system. `PageBreakItem.setGoToPage()` controls the exit of the page **before** its break. Accordingly, SYS02's break redirects completion of SYS01; SYS03's redirects SYS02; SYS04's redirects SYS03. The final break lets SYS04 continue into the final page. Multiple-choice navigation sends the initial selection directly to the selected system's entry page.

## Access and supported behavior

The script sets e-mail collection to `false`, one-response-per-user restrictions to `false`, question shuffling to `false`, and accepts responses. It asks for no name, e-mail, employee ID, or other personal identifier, and does not expose response summaries.

**Responder access requires an account-side check.** FormApp does not provide a current supported setter that universally disables account/domain sign-in requirements. Its old `setRequireLogin()` method is deprecated and is not used. After creation, inspect the form's publishing/responder permissions, allow anyone with the link where available, remove organization-only restrictions, and test the respondent URL while signed out. Workspace administrator policy can prevent anonymous access; publishing alone does not override that policy. No respondent identity is requested by the questionnaire itself.

The script uses only built-in Google Apps Script services: `FormApp` for the questionnaire, `SpreadsheetApp` for its requested response destination, and `PropertiesService` / `LockService` for duplicate protection. The following official references were checked for the methods and behavior used:

- [FormApp: creating an unpublished form](https://developers.google.com/apps-script/reference/forms/form-app)
- [Form: descriptions, item creation, e-mail settings, publishing and spreadsheet destination](https://developers.google.com/apps-script/reference/forms/form)
- [PageBreakItem: page creation and navigation of the preceding page](https://developers.google.com/apps-script/reference/forms/page-break-item)
- [MultipleChoiceItem: required questions and choice-based branching](https://developers.google.com/apps-script/reference/forms/multiple-choice-item)
- [ScaleItem: scale bounds, labels and required responses](https://developers.google.com/apps-script/reference/forms/scale-item)
- [ParagraphTextItem: optional paragraph responses](https://developers.google.com/apps-script/reference/forms/paragraph-text-item)
- [SpreadsheetApp: spreadsheet creation](https://developers.google.com/apps-script/reference/spreadsheet/spreadsheet-app)
- [PropertiesService](https://developers.google.com/apps-script/reference/properties/properties-service) and [LockService](https://developers.google.com/apps-script/reference/lock/lock-service)

## Repeat-execution protection

The default `ALLOW_FORM_CREATION = false` stops execution before accessing any Google service. Even after enabling it, a script lock prevents concurrent creation and Script Properties record the creation attempt, form ID, and spreadsheet ID. A second execution in the same project is blocked rather than creating another form.

The relevant properties are `ADR4AI_CREATION_STATE`, `ADR4AI_FORM_ID`, and `ADR4AI_SPREADSHEET_ID`. If construction fails, the attempt stays recorded and partial artifacts are kept; the script does not delete, recreate, or automatically retry anything. The edit URL is logged immediately after form creation, and the spreadsheet URL immediately after spreadsheet creation, to help inspect partial progress.

For an **intentional additional form**, use a new Apps Script project after reviewing the existing artifacts. Alternatively, deliberately remove the three creation properties in Project Settings only after confirming why a new form is wanted. Enabling the flag in another project or clearing these properties can create another form, so do that only intentionally. No reset or deletion function is included.

## Local validation report

Tests used local JavaScript stand-ins for Google services; no Google account or remote API was contacted. The simulation checks generated item content and routing according to the documented preceding-page semantics. Actual appearance, account permissions, and runtime service limits must be checked when the researcher manually executes and previews the form.

| Requested check | Result |
|---|---|
| Source rows / unique pairs / duplicate pairs | 36 / 36 / 0 |
| Embedded cases / unique pairs | 36 / 36 |
| Embedded pair-set equality with CSV | Exact |
| Cases per system | SYS01: 7; SYS02: 12; SYS03: 8; SYS04: 9 |
| ADR Likert questions | 180, five per case, all required |
| Optional paragraph comments | 36, one per case |
| Q1–Q5 wording | Exact comparison with the supplied instructions |
| Question order | Q1, Q2, Q3, Q4, Q5, COMMENT in every case |
| Requirement field values | All 108 values identical to CSV; requirements displayed once for each of 11 stories |
| Pattern field values | All 144 embedded values identical to CSV |
| ADR field values | All 180 embedded values identical to CSV |
| Forbidden research fields | None in embedded data or generated questions |
| Introduction / final text | Exact requested content |
| System branching / common final section | All four routes passed; no other system encountered |
| E-mail collection | Explicitly disabled |
| Respondent identity | No identity questions; account-side access limitation documented above |
| Creation flag | Exists; defaults to false; disabled execution creates nothing |
| Reexecution / partial failure protection | Both passed; no duplicate form created in simulation |
| Invalid source pairs | Rejected before creation |
| Form item count | 273, including explanatory items and profile questions |
| OpenAI API calls / Google API calls during preparation | 0 / 0 |
| Files created | `create_expert_evaluation_form.gs`, `README.md` |
| Preexisting files modified | 0 |
| Protected artifacts | All preexisting research, evaluation, experiment, catalog and data files unchanged by SHA-256 comparison |
| Commit / push | Neither performed |
