import clickhouse_connect
from dotenv import load_dotenv, find_dotenv 
import os

load_dotenv(find_dotenv())

#Loading our database
db = clickhouse_connect.get_client(
    host=os.getenv("HOST"),
    port=int(os.getenv("PORT")),
    username=os.getenv("USER"),
    password=os.getenv("PASSWORD"),
    database=os.getenv("DATABASE"),
    secure= True
)

def get_schema(client):
    tables = client.query("""
    SELECT
        table,
        name,
        type
    FROM system.columns
    WHERE database = currentDatabase()
    ORDER BY table, position
    """).result_rows
    schema = {}
    for table, column, datatype in tables:
        schema.setdefault(table, []).append(f"{column} {datatype}")
    schema_text = ""
    for table, cols in schema.items():
        schema_text += f"Table: {table}\n"
        schema_text += "\n".join(cols)
        schema_text += "\n\n"
    return schema_text

data_dictionary = """
Healthcare EHR Database Data Dictionary

General Notes
-------------
- Each patient has a unique patient_id.
- Each provider belongs to one department.
- An appointment is a scheduled visit.
- An encounter represents a completed patient visit and is linked to an appointment.
- Most clinical information (diagnoses, vitals, lab results, procedures) is associated with an encounter.
- Insurance claims are generated for encounters.

------------------------------------------------------------

Patients
--------
Stores demographic information for each patient.

Primary Key:
- patient_id

------------------------------------------------------------

Providers
---------
Stores healthcare providers (physicians, specialists, etc.).

Primary Key:
- provider_id

Relationship:
- department_id → Departments.department_id

------------------------------------------------------------

Departments
-----------
Stores hospital or clinic departments.

Primary Key:
- department_id

------------------------------------------------------------

Appointments
------------
Stores scheduled appointments between patients and providers.

Primary Key:
- appointment_id

Relationships:
- patient_id → Patients.patient_id
- provider_id → Providers.provider_id

Status examples:
- Scheduled
- Completed
- Cancelled

------------------------------------------------------------

Encounters
----------
Represents completed clinical visits.

Each encounter is linked to an appointment.

Primary Key:
- encounter_id

Relationships:
- appointment_id → Appointments.appointment_id
- patient_id → Patients.patient_id
- provider_id → Providers.provider_id

------------------------------------------------------------

Problems
--------
Stores diagnoses identified during encounters.

Includes diagnosis status and onset date.

Primary Key:
- problem_id

Relationships:
- patient_id → Patients.patient_id
- encounter_id → Encounters.encounter_id

------------------------------------------------------------

Allergies
---------
Stores patient allergies.

Primary Key:
- allergy_id

Relationship:
- patient_id → Patients.patient_id

------------------------------------------------------------

Vitals
-------
Stores vital signs recorded during an encounter.

Primary Key:
- vital_id

Relationships:
- encounter_id → Encounters.encounter_id
- patient_id → Patients.patient_id

Includes:
- Blood pressure
- Heart rate
- Temperature
- BMI

------------------------------------------------------------

Medications
-----------
Medication master table.

Stores available medications.

Primary Key:
- medication_id

------------------------------------------------------------

Medication_Orders
-----------------
Stores medications prescribed to patients.

Primary Key:
- order_id

Relationships:
- patient_id → Patients.patient_id
- medication_id → Medications.medication_id
- provider_id → Providers.provider_id

------------------------------------------------------------

Lab_Tests
---------
Master table containing laboratory test definitions.

Primary Key:
- test_id

------------------------------------------------------------

Lab_Results
-----------
Stores laboratory test results for patients.

Primary Key:
- result_id

Relationships:
- patient_id → Patients.patient_id
- encounter_id → Encounters.encounter_id
- test_id → Lab_Tests.test_id

------------------------------------------------------------

Procedures
----------
Stores procedures performed during encounters.

Primary Key:
- procedure_id

Relationship:
- encounter_id → Encounters.encounter_id

------------------------------------------------------------

Insurance
---------
Stores each patient's insurance coverage.

Primary Key:
- insurance_id

Relationship:
- patient_id → Patients.patient_id

------------------------------------------------------------

Claims
------
Stores insurance claims submitted for encounters.

Primary Key:
- claim_id

Relationships:
- encounter_id → Encounters.encounter_id
- insurance_id → Insurance.insurance_id

Contains:
- billed_amount
- paid_amount
- claim_status

------------------------------------------------------------

Common Query Patterns
---------------------
- Use Patients for demographics.
- Use Appointments for scheduled visits.
- Use Encounters for completed visits.
- Use Problems to find diagnoses and ICD-10 codes.
- Use Vitals for blood pressure, BMI, temperature, and heart rate.
- Use Medication_Orders to find prescribed medications.
- Use Lab_Results joined with Lab_Tests to retrieve laboratory values.
- Use Procedures for performed procedures.
- Use Claims with Insurance for billing and reimbursement analysis.
- Join Providers with Departments to identify provider specialties and departments.
"""