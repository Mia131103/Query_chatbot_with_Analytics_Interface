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
- An appointment is a scheduled visit between a patient and provider.
- An encounter represents a completed patient visit and is linked to an appointment.
- Most clinical information (diagnoses, vitals, procedures, lab results) is associated with an encounter.
- Insurance claims are generated for encounters.

=================================================================

Patients
--------
Purpose:
Stores demographic information for patients.

Primary Key:
- patient_id

Columns:
- patient_id (Identifier)
- first_name (Text)
- last_name (Text)
- gender (Categorical: Male/Female)
- date_of_birth (Date)
- phone (Text)
- city (Categorical) 
- state (Categorical)

=================================================================

Providers
---------
Purpose:
Stores healthcare providers.

Primary Key:
- provider_id

Relationship:
- department_id → Departments.department_id

Columns:
- provider_id (Identifier)
- first_name (Text)
- last_name (Text)
- specialty (Categorical)
- department_id (Foreign Key)

=================================================================

Departments
-----------
Purpose:
Stores hospital departments.

Primary Key:
- department_id

Columns:
- department_id (Identifier)
- department_name (Categorical)
- location (Categorical)

=================================================================

Appointments
------------
Purpose:
Stores scheduled appointments.

Primary Key:
- appointment_id

Relationships:
- patient_id → Patients.patient_id
- provider_id → Providers.provider_id

Columns:
- appointment_id (Identifier)
- patient_id (Foreign Key)
- provider_id (Foreign Key)
- appointment_date (Date)
- appointment_type (Categorical)
- status (Categorical)

=================================================================

Encounters
----------
Purpose:
Stores completed patient visits.

Primary Key:
- encounter_id

Relationships:
- appointment_id → Appointments.appointment_id
- patient_id → Patients.patient_id
- provider_id → Providers.provider_id

Columns:
- encounter_id (Identifier)
- appointment_id (Foreign Key)
- patient_id (Foreign Key)
- provider_id (Foreign Key)
- encounter_date (Date)
- encounter_type (Categorical)
- chief_complaint (Text)

=================================================================

Problems
--------
Purpose:
Stores diagnoses identified during encounters.

Primary Key:
- problem_id

Relationships:
- patient_id → Patients.patient_id
- encounter_id → Encounters.encounter_id

Columns:
- problem_id (Identifier)
- patient_id (Foreign Key)
- encounter_id (Foreign Key)
- icd10_code (Categorical)
- diagnosis (Categorical)
- status (Categorical)
- onset_date (Date)

=================================================================

Allergies
---------
Purpose:
Stores documented allergies.

Primary Key:
- allergy_id

Relationship:
- patient_id → Patients.patient_id

Columns:
- allergy_id (Identifier)
- patient_id (Foreign Key)
- allergen (Categorical)
- reaction (Categorical)
- severity (Categorical)

=================================================================

Vitals
-------
Purpose:
Stores vital signs measured during encounters.

Primary Key:
- vital_id

Relationships:
- encounter_id → Encounters.encounter_id
- patient_id → Patients.patient_id

Columns:
- vital_id (Identifier)
- encounter_id (Foreign Key)
- patient_id (Foreign Key)
- systolic (Numeric)
- diastolic (Numeric)
- heart_rate (Numeric)
- temperature (Numeric)
- bmi (Numeric)

=================================================================

Medications
-----------
Purpose:
Medication master table.

Primary Key:
- medication_id

Columns:
- medication_id (Identifier)
- medication_name (Categorical)
- generic_name (Categorical)

=================================================================

Medication_Orders
-----------------
Purpose:
Stores medications prescribed to patients.

Primary Key:
- order_id

Relationships:
- patient_id → Patients.patient_id
- medication_id → Medications.medication_id
- provider_id → Providers.provider_id

Columns:
- order_id (Identifier)
- patient_id (Foreign Key)
- medication_id (Foreign Key)
- provider_id (Foreign Key)
- dosage (Text)
- frequency (Categorical)
- start_date (Date)
- end_date (Date)

=================================================================

Lab_Tests
---------
Purpose:
Master list of laboratory tests.

Primary Key:
- test_id

Columns:
- test_id (Identifier)
- test_name (Categorical)
- unit (Categorical)
- normal_low (Numeric)
- normal_high (Numeric)

=================================================================

Lab_Results
-----------
Purpose:
Stores laboratory test results.

Primary Key:
- result_id

Relationships:
- patient_id → Patients.patient_id
- encounter_id → Encounters.encounter_id
- test_id → Lab_Tests.test_id

Columns:
- result_id (Identifier)
- patient_id (Foreign Key)
- test_id (Foreign Key)
- encounter_id (Foreign Key)
- result (Numeric)
- result_date (Date)

=================================================================

Procedures
----------
Purpose:
Stores procedures performed during encounters.

Primary Key:
- procedure_id

Relationship:
- encounter_id → Encounters.encounter_id

Columns:
- procedure_id (Identifier)
- encounter_id (Foreign Key)
- cpt_code (Categorical)
- procedure_name (Categorical)

=================================================================

Insurance
---------
Purpose:
Stores each patient's insurance coverage.

Primary Key:
- insurance_id

Relationship:
- patient_id → Patients.patient_id

Columns:
- insurance_id (Identifier)
- patient_id (Foreign Key)
- payer_name (Categorical)
- plan_type (Categorical)

=================================================================

Claims
------
Purpose:
Stores insurance claims submitted for encounters.

Primary Key:
- claim_id

Relationships:
- encounter_id → Encounters.encounter_id
- insurance_id → Insurance.insurance_id

Columns:
- claim_id (Identifier)
- encounter_id (Foreign Key)
- insurance_id (Foreign Key)
- billed_amount (Numeric)
- paid_amount (Numeric)
- claim_status (Categorical)

=================================================================

Recommended SQL Usage
---------------------
- Use COUNT() on identifiers (e.g., patient_id, encounter_id) to count records.
- Use SUM() and AVG() only on numeric columns (e.g., billed_amount, paid_amount, bmi, systolic, result).
- Group by categorical columns (e.g., diagnosis, specialty, department_name, appointment_type, status, payer_name).
- Use date columns (appointment_date, encounter_date, onset_date, result_date, start_date, end_date, date_of_birth) for trend analysis, filtering, and time-series charts.
- Join Patients to clinical tables using patient_id.
- Join Encounters to clinical event tables (Problems, Procedures, Lab_Results, Vitals) using encounter_id.
- Join Providers to Departments using department_id.
- Join Lab_Results to Lab_Tests using test_id.
- Join Medication_Orders to Medications using medication_id.
- Join Claims to Insurance using insurance_id.
"""