# REHA Connect: User Operations Guide 🚀

This guide outlines the capabilities built into **REHA Connect** — the seamless bidirectional integration between HubSpot and Slack — and provides detailed steps for testing each feature.

---

## 1. Features Overview

**REHA Connect** bridges the gap between your CRM operations and team communications:
*   **🔍 Smart Search in Slack:** Use 9 specialized slash commands (like `/hs`, `/hs-contacts`, `/hs-deals`) to find CRM data instantly.
*   **🎫 Advanced Ticket Management:** Automatically provision private Slack channels for HubSpot tickets and manage them via an interactive Control Panel.
*   **🤖 AI-Powered Insights:** Get instant context via generative AI summaries on CRM cards and link unfurls (with mandatory accuracy disclaimers).
*   **🔔 Automated Notifications:** Real-time alerts for new records, deal stage changes, and high-priority ticket updates.
*   **📝 Quick Actions:** Create HubSpot records (Contacts, Deals, Tasks, Tickets) directly from Slack messages or shortcuts.
*   **🔄 Bidirectional Syncing:** Sync Slack thread replies back to HubSpot as CRM Notes or directly to the Conversations Inbox.
*   **🛡️ Pro-Tier Gating:** Advanced features like the Deal Calculator and Meeting Scheduler are protected for Professional tier users.

---

## 2. Testing Guide: Slack

### A. Slash Commands
Trigger specific or broad searches natively using the unified command set.
1.  **Smart Search:** Type `/hs [query]` for a broad search across all objects.
2.  **Targeted Search:**
    *   `/hs-contacts [name/email]`
    *   `/hs-companies [name/domain]`
    *   `/hs-deals [name]`
    *   `/hs-leads [name/email]`
    *   `/hs-tasks [subject]`
    *   `/hs-tickets [subject/ID]`
    *   `/hs-reports` (view dashboards)
3.  **Help:** Type `/hs-help` to verify connection status.

### B. Ticket Management Workflow
1.  **Create Ticket**: Use the "Create HubSpot Record" shortcut in Slack and select **Ticket**.
2.  **Channel Provisioning**: **Test**: Confirm a new private channel is created (e.g., `#ticket-123-issue-title`) and you are automatically invited.
3.  **Control Panel**: In the new channel, find the Control Panel message.
4.  **Claim & Close**:
    *   Click **Claim Ticket**: **Test**: Confirm the HubSpot Ticket Owner updates to your account.
    *   Click **Close Ticket**: **Test**: Confirm the HubSpot stage updates to "Closed" and the Slack channel is automatically archived.

### C. Quick Records & Shortcuts
1.  **Global Shortcut**: Click the `+` icon in Slack → "Create HubSpot Record".
2.  **Message Action**: Hover over any Slack message → "More actions" (...) → "Create HubSpot Record".
3.  **Test**: Successfully create a Task or Contact and verify it appears in HubSpot immediately.

---

## 3. Testing Guide: HubSpot

### A. AI Insights Card
1.  Open any HubSpot record (Contact, Deal, Company, or Ticket).
2.  Locate the **REHA Connect** card in the sidebar.
3.  **Test**: Confirm the AI Insight block summarizes the record's recent activity and status.
4.  **Disclaimer**: Verify the "AI outputs may be inaccurate" disclaimer is visible at the bottom of the card.

### B. Link Unfurling
1.  Copy the URL of a HubSpot record (e.g., `https://app.hubspot.com/contacts/...`).
2.  Paste it into any Slack channel where the bot is present.
3.  **Test**: Confirm the app "unfurls" the link into a rich preview card with a summary and action buttons.

### C. Notification Threading
1.  Update a HubSpot Ticket (e.g., add a comment or change a stage).
2.  **Test**: Confirm the notification in Slack appears.
3.  **Test**: Reply in the Slack thread of that notification. Verify the reply is synced back to the HubSpot record as a **Note**.

---

## 4. Support & Maintenance

*   **Logs**: Check backend logs or the `/api/health` endpoint for connectivity status.
*   **OAuth**: If tokens expire, the app will prompt for re-authorization via an ephemeral message.
*   **Support**: Reach out to **REHAapps.se@gmail.com** for technical assistance.

© 2026 REHA Apps. Build for scale, automated for speed.
