# EdgeSense: Forest Edge Pressure and Fragmentation Analysis

## Team WFH

* **Medha Prasad** (2022101034)
* **Naveen Kumar G** (2023702016)
* **Pearl Shah** (2022102073)
* **Vinit Mehta** (2022111001)

---

## Setup env

1. Create venv
```bash
python3 -m venv edgesense
```

2. Activate the env
```bash
source ./edgesense/bin/activate
```

3. Install the requirements
```bash
pip install requirements.txt
```

---

## Download dataset

```bash
chmod +x ./scripts/download_data.sh
sh ./download_data.sh
```

---

## Project Overview

Forest ecosystems are increasingly fragmented due to anthropogenic pressures. Fragmentation increases the **edge-to-core ratio**, exposing larger portions of forest patches to external stressors such as:

* Deforestation
* Urban expansion
* Climate variability
* Agricultural encroachment

This project investigates:

> **Do increasing edge-to-core ratios amplify ecological stress signals within forest patches?**

---

## Hypothesis

Forest edges experience higher ecological stress than interior (core) areas due to increased exposure and human interference.

We hypothesize that:

* Higher edge-to-core ratios correlate with stronger ecological stress signals.
* Smaller and fragmented patches exhibit disproportionately higher edge effects.

---

## License

[MIT LICENSE](./LICENSE)
