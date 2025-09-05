
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
import os, pandas as pd
from datetime import datetime, timedelta
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
CAL_DIR = Path(__file__).resolve().parents[1] / "calendar"
EXPORTS_DIR = Path(__file__).resolve().parents[1] / "exports"
OUTBOX_EMAIL = Path(__file__).resolve().parents[1] / "outbox" / "email"
OUTBOX_SMS = Path(__file__).resolve().parents[1] / "outbox" / "sms"
FORMS_DIR = Path(__file__).resolve().parents[1] / "forms"

class Patient(BaseModel):
    name: str
    dob: str
    email: str
    phone: str
    doctor_id: str
    location: str
    is_returning: Optional[bool] = None
    ins_carrier: Optional[str] = None
    ins_member_id: Optional[str] = None
    ins_group: Optional[str] = None

class BookingRequest(BaseModel):
    name: str
    dob: str
    doctor_id: str
    location: str
    is_returning: Optional[bool] = None
    duration_min: Optional[int] = None
    preferred_date: Optional[str] = None

class BookingResult(BaseModel):
    appointment_id: str
    doctor_id: str
    date: str
    start_time: str
    end_time: str
    patient_id: str
    status: str

class EMRTool:
    def __init__(self, patients_csv: str):
        self.df = pd.read_csv(patients_csv, dtype=str)

    def find_patient(self, name: str, dob: str) -> Optional[Dict[str, Any]]:
        sub = self.df[(self.df["name"].str.lower()==name.lower()) & (self.df["dob"]==dob)]
        if sub.empty:
            return None
        return sub.iloc[0].to_dict()

    def upsert_patient(self, p: Patient) -> Dict[str, Any]:
        row = self.find_patient(p.name, p.dob)
        if row is None:
            pid = f"P{len(self.df)+1:03d}"
            new_row = {
                "patient_id": pid,
                "name": p.name,
                "dob": p.dob,
                "email": p.email,
                "phone": p.phone,
                "preferred_doctor_id": p.doctor_id,
                "is_returning": str(p.is_returning is True),
                "ins_carrier": p.ins_carrier or "",
                "ins_member_id": p.ins_member_id or "",
                "ins_group": p.ins_group or ""
            }
            self.df.loc[len(self.df)] = new_row
            self.df.to_csv(DATA_DIR / "patients.csv", index=False)
            return new_row
        else:
            idx = self.df[(self.df["patient_id"]==row["patient_id"])].index[0]
            self.df.loc[idx,"preferred_doctor_id"] = p.doctor_id
            if p.ins_carrier: self.df.loc[idx,"ins_carrier"] = p.ins_carrier
            if p.ins_member_id: self.df.loc[idx,"ins_member_id"] = p.ins_member_id
            if p.ins_group: self.df.loc[idx,"ins_group"] = p.ins_group
            self.df.to_csv(DATA_DIR / "patients.csv", index=False)
            return self.df.loc[idx].to_dict()

class CalendarTool:
    def __init__(self, excel_path: str):
        self.path = excel_path

    def list_free_slots(self, doctor_id: str, location: str, duration_min: int, date_from: Optional[str]=None) -> pd.DataFrame:
        xls = pd.ExcelFile(self.path)
        sch = pd.read_excel(xls, "schedules", dtype=str)
        sch = sch[(sch["doctor_id"]==doctor_id) & (sch["location"].str.lower()==location.lower()) & (sch["slot_status"]=="free")]
        if date_from:
            sch = sch[sch["date"]>=date_from]
        if duration_min == 60:
            pairs = []
            for _, g in sch.groupby(["date"]):
                g2 = g.sort_values("start_time").reset_index(drop=True)
                for i in range(len(g2)-1):
                    row1 = g2.iloc[i]
                    row2 = g2.iloc[i+1]
                    if row1["end_time"] == row2["start_time"]:
                        pairs.append({
                            "doctor_id": row1["doctor_id"],
                            "doctor_name": row1["doctor_name"],
                            "location": row1["location"],
                            "date": row1["date"],
                            "start_time": row1["start_time"],
                            "end_time": row2["end_time"],
                            "slot_status": "free"
                        })
            return pd.DataFrame(pairs)
        return sch

    def book_slot(self, doctor_id: str, date: str, start_time: str, end_time: str, patient_id: str) -> BookingResult:
        xls = pd.ExcelFile(self.path)
        sch = pd.read_excel(xls, "schedules", dtype=str)
        cond = (sch["doctor_id"]==doctor_id) & (sch["date"]==date) & (sch["start_time"]==start_time) & (sch["end_time"]==end_time) & (sch["slot_status"]=="free")
        if cond.sum()==0:
            raise ValueError("Selected slot is no longer available")
        appt_id = f"A{datetime.now().strftime('%Y%m%d%H%M%S')}"
        sch.loc[cond,"slot_status"] = "booked"
        sch.loc[cond,"appointment_id"] = appt_id
        # For 60-min, also mark the adjacent slot if exists
        if datetime.strptime(end_time,"%H:%M") - datetime.strptime(start_time,"%H:%M") == timedelta(minutes=60):
            cond2 = (sch["doctor_id"]==doctor_id) & (sch["date"]==date) & (sch["start_time"]== (datetime.strptime(start_time,"%H:%M")+timedelta(minutes=30)).strftime("%H:%M"))
            sch.loc[cond2,"slot_status"] = "booked"
            sch.loc[cond2,"appointment_id"] = appt_id
        with pd.ExcelWriter(self.path, engine="openpyxl", mode="w") as writer:
            sch.to_excel(writer, index=False, sheet_name="schedules")
        return BookingResult(
            appointment_id=appt_id, doctor_id=doctor_id, date=date, start_time=start_time, end_time=end_time, patient_id=patient_id, status="confirmed"
        )

class InsuranceTool:
    def validate(self, carrier: str, member_id: str, group: str) -> bool:
        if not carrier or not member_id or not group:
            return False
        if len(member_id) < 6:
            return False
        return True

class MessagingTool:
    def send_email(self, to: str, subject: str, body: str):
        ts = datetime.now().isoformat()
        fname = OUTBOX_EMAIL / f"{ts}_{to.replace('@','_at_')}.txt"
        with open(fname,"w") as f:
            f.write(subject + "\n\n" + body)

    def send_sms(self, to: str, body: str):
        ts = datetime.now().isoformat()
        fname = OUTBOX_SMS / f"{ts}_{to}.txt"
        with open(fname,"w") as f:
            f.write(body)

class ExportTool:
    def admin_export(self, booking: BookingResult, patient: Dict[str, Any]):
        EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
        path = EXPORTS_DIR / "admin_review.xlsx"
        row = {
            "appointment_id": booking.appointment_id,
            "patient_id": booking.patient_id,
            "patient_name": patient.get("name",""),
            "dob": patient.get("dob",""),
            "doctor_id": booking.doctor_id,
            "date": booking.date,
            "start_time": booking.start_time,
            "end_time": booking.end_time,
            "status": booking.status,
            "ins_carrier": patient.get("ins_carrier",""),
            "ins_member_id": patient.get("ins_member_id",""),
            "ins_group": patient.get("ins_group","")
        }
        if os.path.exists(path):
            df = pd.read_excel(path)
            df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
        else:
            df = pd.DataFrame([row])
        with pd.ExcelWriter(path, engine="openpyxl", mode="w") as writer:
            df.to_excel(writer, index=False, sheet_name="bookings")
        return str(path)

class ReminderTool:
    def __init__(self):
        self.path = EXPORTS_DIR / "reminders.csv"
        if not os.path.exists(self.path):
            pd.DataFrame(columns=["appointment_id","type","channel","to","status","timestamp","form_filled","visit_confirmed","cancel_reason"]).to_csv(self.path, index=False)

    def log(self, appointment_id: str, type_: str, channel: str, to: str, status: str, form_filled: Optional[bool]=None, visit_confirmed: Optional[bool]=None, cancel_reason: Optional[str]=None):
        df = pd.read_csv(self.path)
        row = {
            "appointment_id": appointment_id,
            "type": type_,
            "channel": channel,
            "to": to,
            "status": status,
            "timestamp": datetime.now().isoformat(),
            "form_filled": form_filled,
            "visit_confirmed": visit_confirmed,
            "cancel_reason": cancel_reason
        }
        df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
        df.to_csv(self.path, index=False)

class AIScheduler:
    def __init__(self):
        self.emr = EMRTool(str(DATA_DIR / "patients.csv"))
        self.cal = CalendarTool(str(CAL_DIR / "doctor_schedules.xlsx"))
        self.ins = InsuranceTool()
        self.msg = MessagingTool()
        self.exp = ExportTool()
        self.rem = ReminderTool()

    def greet_and_collect(self, name: str, dob: str, doctor_id: str, location: str, email: str, phone: str) -> Dict[str, Any]:
        p = Patient(name=name, dob=dob, doctor_id=doctor_id, location=location, email=email, phone=phone)
        found = self.emr.find_patient(name, dob)
        if found:
            p.is_returning = str(found.get("is_returning","False")).lower() == "true"
            p.ins_carrier = found.get("ins_carrier","")
            p.ins_member_id = found.get("ins_member_id","")
            p.ins_group = found.get("ins_group","")
        else:
            p.is_returning = False
        upserted = self.emr.upsert_patient(p)
        return upserted

    def smart_duration(self, is_returning: bool) -> int:
        return 30 if is_returning else 60

    def show_free_slots(self, doctor_id: str, location: str, is_returning: bool, preferred_date: Optional[str]=None) -> pd.DataFrame:
        duration = self.smart_duration(is_returning)
        date_from = preferred_date or datetime.today().date().isoformat()
        return self.cal.list_free_slots(doctor_id, location, duration, date_from)

    def collect_and_validate_insurance(self, carrier: str, member_id: str, group: str) -> bool:
        return self.ins.validate(carrier, member_id, group)

    def confirm_and_book(self, patient_row: Dict[str, Any], date: str, start_time: str, end_time: str) -> BookingResult:
        booking = self.cal.book_slot(patient_row["preferred_doctor_id"], date, start_time, end_time, patient_row["patient_id"])
        path = self.exp.admin_export(booking, patient_row)
        subj = f"Appointment Confirmation {booking.appointment_id}"
        body = f"Dear {patient_row['name']}, your appointment is confirmed on {booking.date} from {booking.start_time} to {booking.end_time}. Appointment ID: {booking.appointment_id}."
        self.msg.send_email(patient_row["email"], subj, body)
        self.msg.send_sms(patient_row["phone"], body)
        return booking

    def send_forms(self, patient_row: Dict[str, Any], booking: BookingResult):
        for form in ["patient_intake_form_template.txt","hipaa_consent_form_template.txt"]:
            subj = f"Forms for Appointment {booking.appointment_id}"
            body = f"Please complete the attached form: {form} and reply before your visit."
            self.msg.send_email(patient_row["email"], subj, body)

    def schedule_reminders(self, patient_row: Dict[str, Any], booking: BookingResult):
        self.rem.log(booking.appointment_id, "reminder_1", "email", patient_row["email"], "queued")
        self.rem.log(booking.appointment_id, "reminder_1", "sms", patient_row["phone"], "queued")
        self.rem.log(booking.appointment_id, "reminder_2", "email", patient_row["email"], "queued", form_filled=False, visit_confirmed=None)
        self.rem.log(booking.appointment_id, "reminder_2", "sms", patient_row["phone"], "queued", form_filled=False, visit_confirmed=None)
        self.rem.log(booking.appointment_id, "reminder_3", "email", patient_row["email"], "queued", form_filled=False, visit_confirmed=False, cancel_reason=None)
        self.rem.log(booking.appointment_id, "reminder_3", "sms", patient_row["phone"], "queued", form_filled=False, visit_confirmed=False, cancel_reason=None)
