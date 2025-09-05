
# Technical Approach

Architecture Overview:
- Streamlit UI invokes AIScheduler service.
- AIScheduler wraps EMRTool, CalendarTool, InsuranceTool, MessagingTool, ExportTool, ReminderTool.
- Patient lookup via CSV EMR, booking into Excel schedule.

Framework Choice:
- LangChain/LangGraph are referenced in requirements for extensibility. Current MVP uses tool-style services to keep the demo fully local and executable.

Integration Strategy:
- Patient Data: CSV as EMR.
- Calendar: Excel file with free/booked slots. Booking writes back to Excel and generates admin export Excel.
- Communication: Simulated Email and SMS by writing files into outbox folders.
- Forms: Text templates emailed after confirmation.
- Reminders: CSV log with required confirmation and form status fields.

Challenges & Solutions:
- Data validation and NLP: Minimal deterministic validation in MVP; can be extended with LLMs.
- File/API management: Excel read/write with openpyxl, file-based outbox to simulate integrations.
- Business logic: 60 min for new, 30 min for returning. Automatic detection from EMR and updates on booking.
- Scheduling & tracking: Reminder entries recorded with types 1, 2, 3 including action checks.
