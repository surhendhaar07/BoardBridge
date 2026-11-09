# BoardBridge pgvector Ingestion Run Log

| Date | Pages | No-text pages | Chunks made | Skipped (duplicate) | New stored | Rows in table | Seconds | Model (dim) | Chunk/overlap |
|---|---|---|---|---|---|---|---|---|---|
| 2026-11-09 | 50 | 0 | 187 | 0 (0 batch, 0 db) | 187 | 187 | 6.8s | sentence-transformers/all-MiniLM-L6-v2 (384) | 1000/150 |
| 2026-11-09 | 50 | 0 | 187 | 187 (0 batch, 187 db) | 0 | 187 | 0.9s | sentence-transformers/all-MiniLM-L6-v2 (384) | 1000/150 |
| 2026-11-09 | 50 | 0 | 187 | 187 (0 batch, 187 db) | 0 | 187 | 0.9s | sentence-transformers/all-MiniLM-L6-v2 (384) | 1000/150 |

## 5 chunks I inspected

### 1. ADXL372 SPI Devicetree Binding
- **Document:** `dts-bindings-sensor-adi-adxl372-spi-yaml`
- **Page:** 1
- **Section:** `General`
- **Chunk index:** 0
- **Status:** Good.
- **Notes:** Captures licensing header and Devicetree SPI hardware description cleanly without broken lines.

### 2. MAX30009 BioZ Mux Configuration
- **Document:** `dts-bindings-sensor-adi-max30009-common-yaml`
- **Page:** 1
- **Section:** `General`
- **Chunk index:** 20
- **Status:** Good.
- **Notes:** Captures bio-impedance register `0x42` mux configurations, enums (`25.7K` to `1000K`), and descriptions. YAML indentation is preserved.

### 3. ADXL355 I2C Accelerometer Binding
- **Document:** `dts-bindings-sensor-adi-adxl355-i2c-yaml`
- **Page:** 1
- **Section:** `General`
- **Chunk index:** 0
- **Status:** Good.
- **Notes:** Succinct Devicetree hardware compatible definition under 200 characters, within `MAX_CHARS`.

### 4. LTC2990 Measurement Mode Register Mapping
- **Document:** `dts-bindings-sensor-adi-adltc2990-yaml`
- **Page:** 1
- **Section:** `compatible: "adi,adltc2990"`
- **Chunk index:** 2
- **Status:** Good.
- **Notes:** Firmware symbol heading `compatible: "adi,adltc2990"` was correctly inherited and injected into the embedding representation.

### 5. BME280 Driver Oversampling & Standby Definitions
- **Document:** `drivers-sensor-bosch-bme280-bme280-h`
- **Page:** 1
- **Section:** `typedef int (*bme280_bus_check_fn)(const union bme280_bus *bus);`
- **Chunk index:** 6
- **Status:** Good.
- **Notes:** Sensor preprocessor `#define` directives and bitshift configurations are fully intact without truncation.

---

## Why 1,000 / 150

1. **Context Window Match**: `sentence-transformers/all-MiniLM-L6-v2` operates with a maximum input limit of 256 word-pieces (tokens). A passage of 1,000 characters approximately maps to ~250 tokens (using the ~4 chars/token heuristic). Keeping `MAX_CHARS = 1000` guarantees that input text utilizes the model's full capacity without suffering silent truncation.
2. **Context Continuity with Overlap**: A 150-character sliding overlap (~35-40 tokens) ensures that function signatures, multi-line C macros, or technical firmware explanations split across boundaries retain context in both adjoining passages.
3. **Word-Bounded Protection**: The chunking engine guarantees that the 150-character overlap starts on a full word boundary, avoiding fragmented tokens.

