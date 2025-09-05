
import streamlit as st
import pandas as pd
from agent.core import AIScheduler
from datetime import datetime

st.set_page_config(page_title="Medical Appointment Scheduler", layout="centered")

st.title("Medical Appointment Scheduling Agent")

with st.form("patient_form"):
    name = st.text_input("Full Name")
    dob = st.date_input("Date of Birth").strftime("%Y-%m-%d")
    email = st.text_input("Email")
    phone = st.text_input("Phone")
    doctor_id = st.selectbox("Doctor", ["D001","D002","D003","D004"])
    location = st.selectbox("Location", ["Chennai Main","Velachery","Tambaram"])
    preferred_date = st.date_input("Preferred Start Date", value=datetime.today()).strftime("%Y-%m-%d")
    submitted = st.form_submit_button("Find Slots")

agent = AIScheduler()

if 'patient_row' not in st.session_state:
    st.session_state['patient_row'] = None

if 'booking' not in st.session_state:
    st.session_state['booking'] = None

if 'slots' not in st.session_state:
    st.session_state['slots'] = None

if submitted:
    patient_row = agent.greet_and_collect(name, dob, doctor_id, location, email, phone)
    st.session_state['patient_row'] = patient_row
    is_returning = str(patient_row.get("is_returning","False")).lower() == "true"
    slots = agent.show_free_slots(doctor_id, location, is_returning, preferred_date)
    st.session_state['slots'] = slots
    st.success(f"Detected {'returning' if is_returning else 'new'} patient. Duration: {'30' if is_returning else '60'} minutes.")
    st.subheader("Available Slots")
    st.dataframe(slots)

if st.session_state['slots'] is not None and st.session_state['patient_row'] is not None:
    st.subheader("Insurance Details")
    carrier = st.text_input("Carrier")
    member_id = st.text_input("Member ID")
    group = st.text_input("Group")
    col1, col2, col3 = st.columns(3)
    with col1:
        date = st.text_input("Date (YYYY-MM-DD)")
    with col2:
        start_time = st.text_input("Start Time (HH:MM)")
    with col3:
        end_time = st.text_input("End Time (HH:MM)")
    if st.button("Validate Insurance and Book"):
        ok = agent.collect_and_validate_insurance(carrier, member_id, group)
        if not ok:
            st.error("Invalid insurance details")
        else:
            pr = st.session_state['patient_row']
            pr["ins_carrier"] = carrier
            pr["ins_member_id"] = member_id
            pr["ins_group"] = group
            try:
                booking = agent.confirm_and_book(pr, date, start_time, end_time)
                st.session_state['booking'] = booking
                st.success(f"Booked. Appointment ID: {booking.appointment_id}")
                agent.send_forms(pr, booking)
                agent.schedule_reminders(pr, booking)
                st.info("Confirmation sent via Email and SMS. Forms dispatched. Reminders scheduled.")
            except Exception as e:
                st.error(str(e))

if st.session_state['booking'] is not None:
    st.subheader("Admin Export File")
    st.write("Check exports/admin_review.xlsx for the record.")
    st.write("Outbox contains messages and reminders.")
