# <Your product name>

> Fill this top section from your Examate project card on Day 1. Replace every line in angle brackets.

## Problem
Firmware engineers developing embedded systems often struggle to identify the correct drivers, devicetree bindings, Kconfig options, and working samples in the large Zephyr RTOS repository. With thousands of source files and hardware configurations, manually finding compatible components can consume significant development time and lead to configuration errors. Existing documentation searches may not provide a complete, board-specific answer connecting the driver, hardware description, and build configuration. BoardBridge solves this problem by combining repository indexing, hybrid code search, and Retrieval-Augmented Generation (RAG) to provide source-cited technical answers. Its AI research agent further investigates complex hardware integration questions and flags claims that cannot be verified against the source code.

## Who it is for
Embedded Firmware Engineer: An engineer at an EV charging startup in Coimbatore migrating controller firmware to a new ARM Cortex-M development board.
Embedded Systems Developer: A developer working with Zephyr RTOS who needs to identify compatible sensors, peripheral drivers, devicetree properties, Kconfig options, and reference implementations quickly.

## Signature feature
Board Bring-up Sheet: Enter a development board and a sensor or peripheral to generate a structured integration report containing the relevant driver source, devicetree compatible string and properties, required Kconfig options, hardware configuration considerations, and related sample code. Each technical claim is linked to supporting source files and line references. Unsupported or unverified claims are explicitly flagged rather than presented as confirmed facts.

## Hardest problem (my interview story)
The hardest engineering challenge in BoardBridge is reliably ingesting and indexing more than 25,000 repository files, including C source code, headers, YAML devicetree bindings, Kconfig files, board definitions, and documentation. Processing such a large repository requires resumable background jobs, progress tracking, retry handling, and duplicate prevention. If a worker crashes halfway through ingestion, the system must resume from the last reliable checkpoint without reprocessing completed files unnecessarily or creating duplicate chunks. I plan to address this through persistent job states, content-based identifiers, idempotent indexing, and automated crash-recovery tests.

## Dataset
| Source | Link | Documents | Pages | Licence / terms |
|---|---|---|---|---|
| Zephyr RTOS source repository | [GitHub](https://github.com/zephyrproject-rtos/zephyr) | 25,000+ target files across C, headers, YAML, Kconfig, devicetree, board definitions, samples, and documentation | Not applicable to source files; record page counts for ingested PDFs or other paginated documents, if included | Apache-2.0 for files covered by that licence; verify individual file headers and third-party component licences |

## 10 real questions
See [docs/QUESTIONS.md](docs/QUESTIONS.md).

## Run it
```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
cp .env.example .env                                 # Windows: copy .env.example .env
uvicorn app.main:app --reload
curl localhost:8000/health
```

## Live link
<Added in Week 2>
