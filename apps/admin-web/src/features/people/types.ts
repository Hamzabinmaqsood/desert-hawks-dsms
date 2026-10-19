export interface Page<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

export interface EmployeeListItem {
  id: string;
  company: string;
  employee_number: string;
  full_name: string;
  employee_type: string;
  employment_status: string;
  branch: string | null;
  branch_name: string | null;
  department: string | null;
  department_name: string | null;
  designation: string | null;
  designation_name: string | null;
  mobile_number: string;
  is_active: boolean;
}

export interface Employee extends EmployeeListItem {
  company: string;
  company_name: string;
  first_name: string;
  middle_name: string;
  last_name: string;
  preferred_name: string;
  gender: string;
  date_of_birth: string | null;
  marital_status: string;
  nationality: string;
  personal_email: string;
  alternate_mobile_number: string;
  employment_type: string;
  joining_date: string;
  confirmation_date: string | null;
  probation_end_date: string | null;
  exit_date: string | null;
  masked_national_identity_number: string;
  national_identity_expiry: string | null;
  created_at: string;
  updated_at: string;
}

export interface OrganizationReference {
  id: string;
  name: string;
  code?: string;
}

export interface EmployeeAddress {
  id: string;
  address_type: string;
  address_line_1: string;
  address_line_2: string;
  city: string;
  province_or_state: string;
  postal_code: string;
  country_code: string;
  is_primary: boolean;
}

export interface EmergencyContact {
  id: string;
  name: string;
  relationship: string;
  mobile_number: string;
  alternate_mobile_number: string;
  address: string;
  is_primary: boolean;
}

export interface StatusHistory {
  id: string;
  previous_status: string;
  new_status: string;
  effective_date: string;
  reason: string;
  changed_by_email: string | null;
  created_at: string;
}

export interface AssignmentHistory {
  id: string;
  branch_name: string | null;
  department_name: string | null;
  designation_name: string | null;
  effective_from: string;
  effective_to: string | null;
  reason: string;
  changed_by_email: string | null;
}

export interface EmployeeDocument {
  id: string;
  title?: string;
  document_type_name?: string;
  file_name?: string;
  status?: string;
  expiry_date?: string | null;
}
