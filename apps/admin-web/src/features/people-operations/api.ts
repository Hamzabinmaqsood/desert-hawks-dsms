import { apiFetch } from "@/lib/api/client";

import type {
  Application,
  Candidate,
  Course,
  CourseVersion,
  Holiday,
  JobRequisition,
  LearningSession,
  LeaveBalance,
  LeaveRequest,
  LeaveType,
  Offer,
  OnboardingCase,
  Page,
  Qualification,
  QualificationType,
  Vacancy,
} from "./types";

const request = <T>(path: string, options?: RequestInit) =>
  apiFetch<T>(path, options);
const query = (values: Record<string, string>) => ({ query: values });
const json = (method: "POST" | "PATCH", body: Record<string, unknown>) => ({
  method,
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});
const encode = (value: string) => encodeURIComponent(value);

export const listRequisitions = (values: Record<string, string> = {}) =>
  apiFetch<Page<JobRequisition>>(
    "/api/recruitment/manpower-requisitions",
    query(values),
  );
export const getRequisition = (id: string) =>
  request<JobRequisition>(
    `/api/recruitment/manpower-requisitions/${encode(id)}`,
  );
export const saveRequisition = (
  id: string | null,
  body: Record<string, unknown>,
) =>
  request<JobRequisition>(
    `/api/recruitment/manpower-requisitions${id ? `/${encode(id)}` : ""}`,
    json(id ? "PATCH" : "POST", body),
  );
export const recruitmentAction = <T>(
  resource: string,
  id: string,
  action: string,
  body = {},
) =>
  request<T>(
    `/api/recruitment/${resource}/${encode(id)}/${action}`,
    json("POST", body),
  );
export const listCandidates = (values: Record<string, string> = {}) =>
  apiFetch<Page<Candidate>>("/api/recruitment/candidates", query(values));
export const getCandidate = (id: string) =>
  request<Candidate>(`/api/recruitment/candidates/${encode(id)}`);
export const saveCandidate = (
  id: string | null,
  body: Record<string, unknown>,
) =>
  request<Candidate>(
    `/api/recruitment/candidates${id ? `/${encode(id)}` : ""}`,
    json(id ? "PATCH" : "POST", body),
  );
export const listApplications = (values: Record<string, string> = {}) =>
  apiFetch<Page<Application>>("/api/recruitment/applications", query(values));
export const getApplication = (id: string) =>
  request<Application>(`/api/recruitment/applications/${encode(id)}`);
export const listVacancies = (values: Record<string, string> = {}) =>
  apiFetch<Page<Vacancy>>("/api/recruitment/vacancies", query(values));
export const listOffers = (application: string) =>
  apiFetch<Page<Offer>>("/api/recruitment/offers", query({ application })).then(
    (v) => v.results,
  );
export const listOnboarding = (application: string) =>
  apiFetch<Page<OnboardingCase>>(
    "/api/recruitment/onboarding",
    query({ application }),
  ).then((v) => v.results);

export const listLeaveTypes = () =>
  request<Page<LeaveType>>("/api/leave/types").then((v) => v.results);
export const listMyLeave = () =>
  request<Page<LeaveRequest>>("/api/leave/me/requests");
export const listLeaveBalances = () =>
  request<LeaveBalance[] | Page<LeaveBalance>>("/api/leave/me/balances").then(
    (v) => (Array.isArray(v) ? v : v.results),
  );
export const listManagerLeave = () =>
  request<Page<LeaveRequest>>("/api/leave/manager/requests");
export const listTeamLeave = () =>
  request<Page<LeaveRequest>>("/api/leave/team/calendar");
export const listHolidays = () => request<Page<Holiday>>("/api/leave/holidays");
export const createLeaveRequest = (body: Record<string, unknown>) =>
  request<LeaveRequest>("/api/leave/me/requests", json("POST", body));
export const leaveAction = (
  resource: "me/requests" | "manager/requests",
  id: string,
  action: string,
  body = {},
) =>
  request<LeaveRequest>(
    `/api/leave/${resource}/${encode(id)}/${action}`,
    json("POST", body),
  );

export const listCourses = (values: Record<string, string> = {}) =>
  apiFetch<Page<Course>>("/api/learning/courses", query(values));
export const getCourse = (id: string) =>
  request<Course>(`/api/learning/courses/${encode(id)}`);
export const listCourseVersions = (course: string) =>
  apiFetch<Page<CourseVersion>>(
    "/api/learning/course-versions",
    query({ course }),
  ).then((value) => value.results);
export const saveCourse = (id: string | null, body: Record<string, unknown>) =>
  request<Course>(
    `/api/learning/courses${id ? `/${encode(id)}` : ""}`,
    json(id ? "PATCH" : "POST", body),
  );
export const listSessions = (values: Record<string, string> = {}) =>
  apiFetch<Page<LearningSession>>("/api/learning/sessions", query(values));
export const getSession = (id: string) =>
  request<LearningSession>(`/api/learning/sessions/${encode(id)}`);
export const saveSession = (id: string | null, body: Record<string, unknown>) =>
  request<LearningSession>(
    `/api/learning/sessions${id ? `/${encode(id)}` : ""}`,
    json(id ? "PATCH" : "POST", body),
  );
export const learningAction = <T>(
  resource: string,
  id: string,
  action: string,
  body = {},
) =>
  request<T>(
    `/api/learning/${resource}/${encode(id)}/${action}`,
    json("POST", body),
  );
export const listQualifications = (employee = "") =>
  apiFetch<Page<Qualification>>(
    "/api/learning/employee-qualifications",
    query(employee ? { employee } : {}),
  );
export const listQualificationTypes = () =>
  apiFetch<Page<QualificationType>>("/api/learning/qualification-types").then(
    (v) => v.results,
  );
