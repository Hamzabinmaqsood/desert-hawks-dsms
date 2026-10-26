export interface Page<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

export interface JobRequisition {
  id: string;
  company: string;
  branch: string | null;
  department: string | null;
  designation: string;
  employee_type: string;
  employment_type: string;
  requested_headcount: number;
  approved_headcount: number | null;
  required_by_date: string | null;
  reason: string;
  status: string;
  created_at: string;
}

export interface Candidate {
  id: string;
  candidate_number: string;
  first_name: string;
  middle_name: string;
  last_name: string;
  mobile_number: string;
  email: string;
  city: string;
  source_type: string;
  status: string;
  notes: string;
}

export interface Application {
  id: string;
  application_number: string;
  candidate: string;
  vacancy: string;
  status: string;
  applied_at: string | null;
  availability_date: string | null;
  current_employer: string;
  current_job_title: string;
  total_experience_months: number | null;
  hired_employee: string | null;
}

export interface Vacancy {
  id: string;
  vacancy_code: string;
  title: string;
  status: string;
  number_of_positions: number;
  positions_filled: number;
  opening_date: string;
}

export interface Offer {
  id: string;
  application: string;
  offer_number: string;
  proposed_joining_date: string;
  offer_expiry_date: string | null;
  status: string;
  terms_summary: string;
  offered_base_salary?: string;
}

export interface OnboardingCase {
  id: string;
  application: string;
  candidate: string;
  proposed_employee_number: string;
  proposed_joining_date: string;
  status: string;
}

export interface LeaveType {
  id: string;
  code: string;
  name: string;
  unit: string;
  requires_balance: boolean;
  requires_attachment: boolean;
  allow_partial_day: boolean;
}

export interface LeaveRequest {
  id: string;
  request_number: string;
  employee: string;
  employee_name?: string;
  leave_type: string;
  leave_type_name?: string;
  starts_at: string;
  ends_at: string;
  requested_units: string;
  approved_units: string | null;
  reason?: string;
  status: string;
  emergency_request: boolean;
}

export interface LeaveBalance {
  leave_type: string;
  leave_type_name: string;
  unit: string;
  entitled: string;
  reserved: string;
  taken: string;
  available: string;
}

export interface Holiday {
  id: string;
  date: string;
  name: string;
  holiday_type: string;
  is_full_day: boolean;
  calendar_name: string;
}

export interface Course {
  id: string;
  company: string;
  category: string | null;
  code: string;
  title: string;
  description: string;
  objective: string;
  delivery_method: string;
  duration_hours: string;
  status: string;
  requires_assessment: boolean;
  produces_certificate: boolean;
}

export interface CourseVersion {
  id: string;
  course: string;
  version_number: number;
  effective_from: string;
  effective_to: string | null;
  is_current: boolean;
}

export interface LearningSession {
  id: string;
  session_number: string;
  course: string;
  course_version: string;
  program: string | null;
  start_datetime: string;
  end_datetime: string;
  enrollment_deadline: string | null;
  capacity: number;
  status: string;
  notes: string;
}

export interface Qualification {
  id: string;
  employee: string;
  qualification_type: string;
  source: string;
  obtained_on: string;
  expires_on: string | null;
  status: string;
  notes: string;
}

export interface QualificationType {
  id: string;
  code: string;
  name: string;
  is_active: boolean;
}
