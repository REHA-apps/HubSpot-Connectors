Use Case 1: The "High-Value Deal Idle" Alert
Notify the sales team if a large deal hasn't been touched in over a week.

Go to Automation > Workflows > Create Workflow > Deal-based > Blank workflow.
Set Trigger:
Click Set up triggers.
Filter type: Deal properties
Add condition 1: Amount is greater than 10000 (or your high-value threshold)
Add condition 2: Last activity date is more than 7 days ago
Add condition 3: Deal stage is none of Closed Won or Closed Lost.
Add Action (The custom app part!):
Click the + (plus) icon.
Scroll down the right sidebar to Connected Apps and select your app, then choose Send Slack Message.
Configure the Action:
Slack Channel ID: C0123456789 (Your sales manager channel or #general).
Message: Type something like: "🚨 Warning: A high-value deal is slipping! "[Insert token: Deal Name]" for $[Insert token: Amount] assigned to [Insert token: Deal Owner] hasn't been touched in 7 days."
Turn On!
Use Case 2: The "VIP Customer Support Urgent" Alert
Instantly page the support team via Slack if a high-priority ticket is created by a major client.

Go to Automation > Workflows > Create Workflow > Ticket-based > Blank workflow.
Set Trigger:
Filter type: Ticket properties
Priority is any of High
AND Filter type: Company properties (associated company)
Annual Revenue is greater than 1,000,000 (or Lifecycle stage is Customer).
Add Action:
Click the + icon, scroll to Connected Apps > Your App > Send Slack Message.
Configure the Action:
Slack Channel ID: Your #urgent-support channel ID.
Message: "🔥 URGENT TICKET: [Insert token: Ticket Name] from a VIP client! "[Insert token: Ticket Description]". Priority is set to HIGH."
Turn On!
Use Case 3: The "Closed-Won Celebration" Post
Automatically blast the company #celebrations channel whenever a deal is won.

Go to Automation > Workflows > Create Workflow > Deal-based > Blank workflow.
Set Trigger:
Filter type: Deal properties
Deal stage is any of Closed Won.
Add Action:
Click the + icon, scroll to Connected Apps > Your App > Send Slack Message.
Configure the Action:
Slack Channel ID: Your company's #celebrations or #wins channel ID.
Message: "🎉 BOOM! [Insert token: Deal Owner] just closed "[Insert token: Deal Name]" for $[Insert token: Amount]! Great job everyone! 🚀"
Turn On!
The Recipe Checklist to Build Any Workflow:
If you want to invent your own workflows, the formula is always exactly the same:

Trigger: "When should this happen?" (HubSpot Handles this entirely)
Logic/Delays: "Should I wait 3 days? Should I check if the deal is assigned?" (HubSpot standard actions)
Action: "Send the data over to my FastAPI Backend." (Your App's Send Slack Message action at the bottom of the actions list).
Because your backend parses whatever you write in the "Message" field and posts it directly to the Slack API, you have unlimited flexibility.

Here is a step-by-step guide to setting up a custom HubSpot workflow specifically to test the Email to Slack Threading feature we just implemented.

Phase 1: Create the Workflow in HubSpot
Log in to HubSpot: Navigate to Automation from the top menu and select Workflows.
Create New Workflow: Click the Create Workflow button in the top right, and choose From scratch.
Select Object Type: Since we want to trigger this when an email is logged to a Contact, select Contact-based and choose Blank workflow, then click Next.
Phase 2: Set the Trigger (Email Logged)
Add Trigger: Click Set up triggers.
Choose Filter: In the left sidebar under "Filter criteria", select Activity properties.
Filter by Email:
Search for Activity type and select is any of.
Choose Email sent to contact (and optionally Email received from contact if you want inbound emails to trigger as well).
Save: Click Apply filter and then Save.
Note on Re-enrollment: By default, HubSpot workflows only trigger once per contact. If you want this to trigger every time the same contact gets a new email, click the Re-enrollment tab on the trigger page and enable "Re-enroll contacts when they meet the trigger criteria".
Phase 3: Add the Custom "Send Slack Message" Action
Add Action: Click the (+) icon below your trigger to add an action.
Find the Connector App: In the left panel, scroll down to the Connected Apps section and select your custom app (e.g., "HubSpot CRM Connectors").
Select the Action: Click the Send Slack Message action.
Configure Action Properties:
Slack Channel ID: Enter the ID of your test Slack channel. (You can find this by going to Slack -> clicking the channel name at the top -> scrolling to the bottom of the "About" modal. It starts with a C, like C01ABCD2345).
Message Content: You can construct a dynamic message summarizing the new email. Click the Contact Token icon (the small orange tag) to inject properties. For example: <@your_slack_username> A new email was logged for *{{Contact Name}}*! \nTheir details: \n*Email:* {{Contact Email}} \n*Lifecycle Stage:* {{Lifecycle Stage}}
Save: Click Save on the action.
Turn it On: In the top right corner of the workflow builder, click Review and Publish, then turn the workflow ON.
Phase 4: The End-to-End Test
Trigger the Condition: Go to any test Contact Record in HubSpot. Click the Emails tab and manually log a test email (or send an actual one).
Check Slack: Within a few seconds, the automated Slack message you configured in the workflow should drop into your specified Slack channel.
Reply in Thread: In Slack, click Reply in thread on that specific automated message. Type a message like: "I will follow up with them tomorrow."
Verify the Sync: Refresh the Contact record page in HubSpot. Look at the central timeline. You should see a brand new CRM Note generated by the integration that says:
Slack Reply from @your_name: I will follow up with them tomorrow.

If you don't receive the notification, check the History tab of the workflow in HubSpot to make sure the contact properly enrolled when you logged the email!
