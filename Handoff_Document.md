## Project Overview
A mobile-first, edge-to-cloud Streamlit app that provides real-time QA/QC validation for field data sampling. Designed to operate in low-connectivity environments, it features on-device anomaly detection, Voice SOPs, OCR digitization, and automated Chain of Custody reporting. 

## Hybrid Architecture & Folder Structure
This application uses an industry-standard hybrid architecture to ensure resilience when internet access drops in the field [1].

*   `/edge_app` **(The Field Interface):** The offline mobile Streamlit app. It runs local, sub-10B parameter AI models [2] to handle real-time sensor anomaly detection and Voice SOPs entirely without an internet connection [1, 3].
*   `/gateway_sync` **(The Bridge):** Scripts that securely aggregate and buffer field data locally while offline, automatically tunneling it to the central database the moment internet connectivity is restored [1].
*   `/cloud_analytics` **(The Heavy Lifter):** Centralized dashboards, GIS mapping, and predictive analytics that run on the synced historical data to forecast future infrastructure issues [1].

## Team Roles & Responsibilities
*   **The Field Ops Lead:** Owns the `/edge_app` directory. Focuses on the mobile Streamlit UI, ensuring buttons are huge and glove-friendly, and integrates OCR (Optical Character Recognition) so techs can digitize meters via their phone cameras [4-6].
*   **The QA/QC Manager:** Owns the on-device safety rules [4]. Implements local AI to flag physically impossible readings (e.g., pH limits) and builds the local Voice SOP knowledge base [3].
*   **The Data Historian:** Owns the `/gateway_sync` directory. Generates the realistic historical dataset and builds the buffering logic to handle the offline-to-online data sync [1, 4].
*   **The Visualization Specialist:** Owns the `/cloud_analytics` directory. Builds the centralized office dashboards, interactive maps, and predictive models using the aggregated data [1, 4].
*   **The Report Formatter:** Owns the automated compliance workflows. Uses **n8n** (a visual workflow automation tool) to detect when new data hits the cloud, automatically generating the PDF Chain of Custody and posting a notification to Slack or Email [4, 7, 8].

## Collaborative "Vibe Coding" Rules
1.  **Write Intent, Not Syntax:** Act like a Product Manager. Clearly describe what you want the user to see and do in Cursor's Composer, and let the AI handle the actual code generation [9].
2.  **Version Control:** Always pull the latest code from GitHub (`git pull`) before starting your work session to avoid stepping on each other's toes.
3.  **The Prompt Log:** Document every single prompt you use—both the ones that succeed and the ones that fail. This log is the most important deliverable for the final project [9].

