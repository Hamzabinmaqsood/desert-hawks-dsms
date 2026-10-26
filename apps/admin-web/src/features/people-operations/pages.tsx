"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  useCallback,
  useEffect,
  useState,
  type FormEvent,
  type ReactNode,
} from "react";

import { PageHeader } from "@/components/layout/page-header";
import { Button } from "@/components/ui/button";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/states";
import { useAuth } from "@/features/auth/auth-context";
import { listReferences } from "@/features/people/api";
import type { OrganizationReference } from "@/features/people/types";
import { ApiError } from "@/lib/api/client";

import {
  createLeaveRequest,
  getApplication,
  getCandidate,
  getCourse,
  getRequisition,
  getSession,
  learningAction,
  leaveAction,
  listApplications,
  listCandidates,
  listCourses,
  listCourseVersions,
  listHolidays,
  listLeaveBalances,
  listLeaveTypes,
  listManagerLeave,
  listMyLeave,
  listOffers,
  listOnboarding,
  listQualifications,
  listQualificationTypes,
  listRequisitions,
  listSessions,
  listTeamLeave,
  listVacancies,
  recruitmentAction,
  saveCandidate,
  saveCourse,
  saveRequisition,
  saveSession,
} from "./api";
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

const selectedCompany = (auth: ReturnType<typeof useAuth>) =>
  auth.company_context.selected_company?.id ?? "";
const humanize = (value: string) =>
  value
    .replaceAll("_", " ")
    .toLowerCase()
    .replace(/^./, (letter) => letter.toUpperCase());
const messageFor = (error: unknown, fallback: string) =>
  error instanceof ApiError ? error.message : fallback;

function Status({ value }: { value: string }) {
  return (
    <span className={`status-badge status-${value.toLowerCase()}`}>
      {humanize(value)}
    </span>
  );
}

function WorkspaceTabs({ children }: { children: ReactNode }) {
  return (
    <div className="quick-actions" aria-label="Workspace sections">
      {children}
    </div>
  );
}

export function RecruitmentPage({
  searchParams,
}: {
  searchParams: Record<string, string>;
}) {
  const auth = useAuth();
  const [data, setData] = useState<{
    requisitions: Page<JobRequisition>;
    candidates: Page<Candidate>;
    applications: Page<Application>;
    vacancies: Page<Vacancy>;
  } | null>(null);
  const [error, setError] = useState("");
  const company = selectedCompany(auth);
  const canView = auth.canAny(
    "recruitment.view_manpowerrequisition",
    "recruitment.view_candidate",
    "recruitment.view_candidateapplication",
  );
  useEffect(() => {
    if (!canView) return;
    let current = true;
    Promise.all([
      listRequisitions(searchParams),
      listCandidates(searchParams),
      listApplications(searchParams),
      listVacancies({ status: "OPEN", ordering: "opening_date" }),
    ])
      .then(
        ([requisitions, candidates, applications, vacancies]) =>
          current &&
          setData({ requisitions, candidates, applications, vacancies }),
      )
      .catch(() => current && setError("Recruitment could not be loaded."));
    return () => {
      current = false;
    };
  }, [canView, company, searchParams]);
  if (!canView)
    return (
      <ErrorState message="You do not have permission to view Recruitment." />
    );
  return (
    <>
      <PageHeader
        title="Recruitment"
        description="Job Requisitions, candidates, applications, offers, and onboarding."
        actions={
          auth.can("recruitment.add_manpowerrequisition") ? (
            <Link className="button" href="/recruitment/requisitions/new">
              New Job Requisition
            </Link>
          ) : undefined
        }
      />
      <WorkspaceTabs>
        {auth.can("recruitment.add_candidate") ? (
          <Link href="/recruitment/candidates/new">Add candidate</Link>
        ) : null}
      </WorkspaceTabs>
      <form className="invoice-filters" action="/recruitment">
        <label>
          Search
          <input
            name="search"
            defaultValue={searchParams.search}
            placeholder="Requisition, candidate, or vacancy"
          />
        </label>
        <label>
          Status
          <input
            name="status"
            defaultValue={searchParams.status}
            placeholder="Status"
          />
        </label>
        <Button>Filter</Button>
      </form>
      {error ? (
        <ErrorState message={error} />
      ) : !data ? (
        <LoadingState label="Loading Recruitment..." />
      ) : (
        <div className="dashboard-grid">
          <section className="dashboard-widget">
            <h2>Job Requisitions</h2>
            {data.requisitions.results.length ? (
              <div className="table-wrap">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Role</th>
                      <th>Headcount</th>
                      <th>Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.requisitions.results.map((item) => (
                      <tr key={item.id}>
                        <td>
                          <Link href={`/recruitment/requisitions/${item.id}`}>
                            {item.reason}
                          </Link>
                        </td>
                        <td>{item.requested_headcount}</td>
                        <td>
                          <Status value={item.status} />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <EmptyState message="No Job Requisitions match this filter." />
            )}
          </section>
          <section className="dashboard-widget">
            <h2>Open vacancies</h2>
            {data.vacancies.results.length ? (
              <ul className="setup-list">
                {data.vacancies.results.map((item) => (
                  <li key={item.id}>
                    {item.title} · {item.positions_filled}/
                    {item.number_of_positions} filled
                  </li>
                ))}
              </ul>
            ) : (
              <p>No open vacancies.</p>
            )}
          </section>
          <section className="dashboard-widget">
            <h2>Candidates</h2>
            {data.candidates.results.length ? (
              <ul className="setup-list">
                {data.candidates.results.map((item) => (
                  <li key={item.id}>
                    <Link href={`/recruitment/candidates/${item.id}`}>
                      {item.first_name} {item.last_name}
                    </Link>{" "}
                    <Status value={item.status} />
                  </li>
                ))}
              </ul>
            ) : (
              <p>No candidates.</p>
            )}
          </section>
          <section className="dashboard-widget">
            <h2>Applications requiring attention</h2>
            {data.applications.results.length ? (
              <ul className="setup-list">
                {data.applications.results.map((item) => (
                  <li key={item.id}>
                    <Link href={`/recruitment/applications/${item.id}`}>
                      {item.application_number}
                    </Link>{" "}
                    <Status value={item.status} />
                  </li>
                ))}
              </ul>
            ) : (
              <p>No applications.</p>
            )}
          </section>
        </div>
      )}
    </>
  );
}

function RequisitionForm({ item }: { item?: JobRequisition }) {
  const auth = useAuth();
  const router = useRouter();
  const company = selectedCompany(auth);
  const [references, setReferences] = useState<
    Record<string, OrganizationReference[]>
  >({});
  const [values, setValues] = useState({
    branch: item?.branch ?? "",
    department: item?.department ?? "",
    designation: item?.designation ?? "",
    employee_type: item?.employee_type ?? "OFFICE_STAFF",
    employment_type: item?.employment_type ?? "PERMANENT",
    requested_headcount: String(item?.requested_headcount ?? 1),
    required_by_date: item?.required_by_date ?? "",
    reason: item?.reason ?? "",
  });
  const [message, setMessage] = useState("");
  const [pending, setPending] = useState(false);
  useEffect(() => {
    let current = true;
    Promise.all([
      listReferences("branches"),
      listReferences("departments"),
      listReferences("designations"),
    ])
      .then(
        ([branches, departments, designations]) =>
          current && setReferences({ branches, departments, designations }),
      )
      .catch(
        () =>
          current && setMessage("Organization references could not be loaded."),
      );
    return () => {
      current = false;
    };
  }, [company]);
  const permission = item
    ? "recruitment.change_manpowerrequisition"
    : "recruitment.add_manpowerrequisition";
  if (!auth.can(permission))
    return (
      <ErrorState message="You do not have permission to manage Job Requisitions." />
    );
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (pending) return;
    setPending(true);
    setMessage("");
    try {
      const saved = await saveRequisition(item?.id ?? null, {
        ...values,
        branch: values.branch || null,
        department: values.department || null,
        requested_headcount: Number(values.requested_headcount),
      });
      router.push(`/recruitment/requisitions/${saved.id}`);
    } catch (reason) {
      setMessage(messageFor(reason, "The Job Requisition could not be saved."));
    } finally {
      setPending(false);
    }
  }
  return (
    <form className="invoice-form" onSubmit={submit}>
      {message ? (
        <p className="form-error" role="alert">
          {message}
        </p>
      ) : null}
      <label className="form-field">
        <span>Designation *</span>
        <select
          required
          value={values.designation}
          onChange={(e) =>
            setValues({ ...values, designation: e.target.value })
          }
        >
          <option value="">Select designation</option>
          {references.designations?.map((v) => (
            <option key={v.id} value={v.id}>
              {v.name}
            </option>
          ))}
        </select>
      </label>
      <label className="form-field">
        <span>Branch</span>
        <select
          value={values.branch}
          onChange={(e) => setValues({ ...values, branch: e.target.value })}
        >
          <option value="">Company-wide</option>
          {references.branches?.map((v) => (
            <option key={v.id} value={v.id}>
              {v.name}
            </option>
          ))}
        </select>
      </label>
      <label className="form-field">
        <span>Department</span>
        <select
          value={values.department}
          onChange={(e) => setValues({ ...values, department: e.target.value })}
        >
          <option value="">No department</option>
          {references.departments?.map((v) => (
            <option key={v.id} value={v.id}>
              {v.name}
            </option>
          ))}
        </select>
      </label>
      <label className="form-field">
        <span>Employee type *</span>
        <input
          required
          value={values.employee_type}
          onChange={(e) =>
            setValues({ ...values, employee_type: e.target.value })
          }
        />
      </label>
      <label className="form-field">
        <span>Employment type *</span>
        <select
          required
          value={values.employment_type}
          onChange={(e) =>
            setValues({ ...values, employment_type: e.target.value })
          }
        >
          <option>PERMANENT</option>
          <option>CONTRACT</option>
          <option>TEMPORARY</option>
        </select>
      </label>
      <label className="form-field">
        <span>Requested headcount *</span>
        <input
          required
          min="1"
          type="number"
          value={values.requested_headcount}
          onChange={(e) =>
            setValues({ ...values, requested_headcount: e.target.value })
          }
        />
      </label>
      <label className="form-field">
        <span>Required by</span>
        <input
          type="date"
          value={values.required_by_date}
          onChange={(e) =>
            setValues({ ...values, required_by_date: e.target.value })
          }
        />
      </label>
      <label className="form-field">
        <span>Business reason *</span>
        <textarea
          required
          value={values.reason}
          onChange={(e) => setValues({ ...values, reason: e.target.value })}
        />
      </label>
      <div className="form-actions">
        <Button disabled={pending}>
          {pending ? "Saving..." : "Save Job Requisition"}
        </Button>
        <Link className="button button-secondary" href="/recruitment">
          Cancel
        </Link>
      </div>
    </form>
  );
}

export function RequisitionCreatePage() {
  return (
    <>
      <PageHeader
        title="New Job Requisition"
        description="Request Company headcount using existing organization roles."
      />
      <RequisitionForm />
    </>
  );
}

export function RequisitionDetailPage({ id }: { id: string }) {
  const auth = useAuth();
  const [item, setItem] = useState<JobRequisition | null>(null);
  const [message, setMessage] = useState("");
  const company = selectedCompany(auth);
  const load = useCallback(
    () =>
      getRequisition(id)
        .then(setItem)
        .catch(() => setMessage("The Job Requisition could not be loaded.")),
    [id],
  );
  useEffect(() => {
    void load();
  }, [company, load]);
  async function act(action: string) {
    if (
      (action === "approve" || action === "reject") &&
      !window.confirm(`${humanize(action)} this Job Requisition?`)
    )
      return;
    try {
      const body =
        action === "approve"
          ? { approved_headcount: item?.requested_headcount }
          : action === "reject"
            ? { reason: "Rejected after review" }
            : {};
      setItem(
        await recruitmentAction<JobRequisition>(
          "manpower-requisitions",
          id,
          action,
          body,
        ),
      );
    } catch (reason) {
      setMessage(messageFor(reason, "The workflow action failed."));
    }
  }
  if (message && !item) return <ErrorState message={message} />;
  if (!item) return <LoadingState label="Loading Job Requisition..." />;
  return (
    <>
      <PageHeader title="Job Requisition" description={item.reason} />
      <Status value={item.status} />
      <dl className="detail-grid">
        <div>
          <dt>Requested headcount</dt>
          <dd>{item.requested_headcount}</dd>
        </div>
        <div>
          <dt>Approved headcount</dt>
          <dd>{item.approved_headcount ?? "Pending"}</dd>
        </div>
        <div>
          <dt>Required by</dt>
          <dd>{item.required_by_date ?? "Not specified"}</dd>
        </div>
      </dl>
      {message ? (
        <p className="form-error" role="alert">
          {message}
        </p>
      ) : null}
      <div className="quick-actions">
        {item.status === "DRAFT" &&
        auth.can("recruitment.change_manpowerrequisition") ? (
          <Button onClick={() => void act("submit")}>Submit</Button>
        ) : null}
        {item.status === "SUBMITTED" &&
        auth.can("recruitment.approve_requisition") ? (
          <>
            <Button onClick={() => void act("approve")}>Approve</Button>
            <Button
              className="button-secondary"
              onClick={() => void act("reject")}
            >
              Reject
            </Button>
          </>
        ) : null}
        <Link href="/recruitment">Back to Recruitment</Link>
      </div>
    </>
  );
}

function CandidateForm({ item }: { item?: Candidate }) {
  const auth = useAuth();
  const router = useRouter();
  const [values, setValues] = useState({
    first_name: item?.first_name ?? "",
    middle_name: item?.middle_name ?? "",
    last_name: item?.last_name ?? "",
    mobile_number: item?.mobile_number ?? "",
    email: item?.email ?? "",
    city: item?.city ?? "",
    source_type: item?.source_type ?? "WEBSITE",
    notes: item?.notes ?? "",
  });
  const [message, setMessage] = useState("");
  const [pending, setPending] = useState(false);
  if (
    !auth.can(
      item ? "recruitment.change_candidate" : "recruitment.add_candidate",
    )
  )
    return (
      <ErrorState message="You do not have permission to manage candidates." />
    );
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (pending) return;
    setPending(true);
    try {
      const saved = await saveCandidate(item?.id ?? null, values);
      router.push(`/recruitment/candidates/${saved.id}`);
    } catch (reason) {
      setMessage(messageFor(reason, "The candidate could not be saved."));
    } finally {
      setPending(false);
    }
  }
  return (
    <form className="invoice-form" onSubmit={submit}>
      {message ? (
        <p className="form-error" role="alert">
          {message}
        </p>
      ) : null}
      <label className="form-field">
        <span>First name *</span>
        <input
          required
          value={values.first_name}
          onChange={(e) => setValues({ ...values, first_name: e.target.value })}
        />
      </label>
      <label className="form-field">
        <span>Last name</span>
        <input
          value={values.last_name}
          onChange={(e) => setValues({ ...values, last_name: e.target.value })}
        />
      </label>
      <label className="form-field">
        <span>Mobile number *</span>
        <input
          required
          value={values.mobile_number}
          onChange={(e) =>
            setValues({ ...values, mobile_number: e.target.value })
          }
        />
      </label>
      <label className="form-field">
        <span>Email</span>
        <input
          type="email"
          value={values.email}
          onChange={(e) => setValues({ ...values, email: e.target.value })}
        />
      </label>
      <label className="form-field">
        <span>City</span>
        <input
          value={values.city}
          onChange={(e) => setValues({ ...values, city: e.target.value })}
        />
      </label>
      <label className="form-field">
        <span>Source *</span>
        <select
          value={values.source_type}
          onChange={(e) =>
            setValues({ ...values, source_type: e.target.value })
          }
        >
          <option>WEBSITE</option>
          <option>REFERRAL</option>
          <option>WALK_IN</option>
          <option>AGENCY</option>
        </select>
      </label>
      <label className="form-field">
        <span>Notes</span>
        <textarea
          value={values.notes}
          onChange={(e) => setValues({ ...values, notes: e.target.value })}
        />
      </label>
      <div className="form-actions">
        <Button disabled={pending}>
          {pending ? "Saving..." : "Save candidate"}
        </Button>
        <Link className="button button-secondary" href="/recruitment">
          Cancel
        </Link>
      </div>
    </form>
  );
}
export function CandidateCreatePage() {
  return (
    <>
      <PageHeader
        title="Add candidate"
        description="Create a Company-scoped candidate profile."
      />
      <CandidateForm />
    </>
  );
}
export function CandidateDetailPage({ id }: { id: string }) {
  const auth = useAuth();
  const company = selectedCompany(auth);
  const [item, setItem] = useState<Candidate | null>(null);
  useEffect(() => {
    void getCandidate(id).then(setItem);
  }, [company, id]);
  if (!item) return <LoadingState label="Loading candidate..." />;
  return (
    <>
      <PageHeader
        title={`${item.first_name} ${item.last_name}`}
        description={item.candidate_number}
      />
      <Status value={item.status} />
      <dl className="detail-grid">
        <div>
          <dt>Mobile</dt>
          <dd>{item.mobile_number}</dd>
        </div>
        <div>
          <dt>Email</dt>
          <dd>{item.email || "Not provided"}</dd>
        </div>
        <div>
          <dt>Source</dt>
          <dd>{humanize(item.source_type)}</dd>
        </div>
      </dl>
      <Link href="/recruitment">Back to Recruitment</Link>
    </>
  );
}

export function ApplicationDetailPage({ id }: { id: string }) {
  const auth = useAuth();
  const company = selectedCompany(auth);
  const [item, setItem] = useState<Application | null>(null);
  const [offers, setOffers] = useState<Offer[]>([]);
  const [onboarding, setOnboarding] = useState<OnboardingCase[]>([]);
  const [message, setMessage] = useState("");
  useEffect(() => {
    let current = true;
    Promise.all([getApplication(id), listOffers(id), listOnboarding(id)])
      .then(([application, offerRows, onboardingRows]) => {
        if (current) {
          setItem(application);
          setOffers(offerRows);
          setOnboarding(onboardingRows);
        }
      })
      .catch(
        () => current && setMessage("The application could not be loaded."),
      );
    return () => {
      current = false;
    };
  }, [company, id]);
  async function transition(status: string) {
    if (
      ["REJECTED", "WITHDRAWN"].includes(status) &&
      !window.confirm(`${humanize(status)} this application?`)
    )
      return;
    try {
      setItem(
        await recruitmentAction<Application>("applications", id, "transition", {
          status,
        }),
      );
    } catch (reason) {
      setMessage(messageFor(reason, "The application could not be advanced."));
    }
  }
  async function runOfferAction(offer: Offer, action: string) {
    if (
      ["issue", "accept", "begin-onboarding"].includes(action) &&
      !window.confirm(`${humanize(action)} for this offer?`)
    )
      return;
    try {
      if (action === "begin-onboarding") {
        const created = await recruitmentAction<OnboardingCase>(
          "offers",
          offer.id,
          action,
        );
        setOnboarding((current) => [created, ...current]);
      } else {
        const updated = await recruitmentAction<Offer>(
          "offers",
          offer.id,
          action,
        );
        setOffers((current) =>
          current.map((row) => (row.id === updated.id ? updated : row)),
        );
      }
    } catch (reason) {
      setMessage(messageFor(reason, "The offer workflow action failed."));
    }
  }
  async function runOnboardingAction(row: OnboardingCase, action: string) {
    if (!window.confirm(`${humanize(action)} this candidate?`)) return;
    try {
      if (action === "hire") {
        const employeeNumber = window.prompt(
          "Employee number",
          row.proposed_employee_number,
        );
        if (!employeeNumber) return;
        const result = await recruitmentAction<{ employee_id: string }>(
          "onboarding",
          row.id,
          action,
          { employee_number: employeeNumber },
        );
        setItem((current) =>
          current
            ? {
                ...current,
                status: "HIRED",
                hired_employee: result.employee_id,
              }
            : current,
        );
        setOnboarding((current) =>
          current.map((entry) =>
            entry.id === row.id ? { ...entry, status: "COMPLETED" } : entry,
          ),
        );
      } else {
        const updated = await recruitmentAction<OnboardingCase>(
          "onboarding",
          row.id,
          action,
        );
        setOnboarding((current) =>
          current.map((entry) => (entry.id === updated.id ? updated : entry)),
        );
      }
    } catch (reason) {
      setMessage(messageFor(reason, "The onboarding workflow action failed."));
    }
  }
  if (message && !item) return <ErrorState message={message} />;
  if (!item) return <LoadingState label="Loading application..." />;
  return (
    <>
      <PageHeader
        title={item.application_number}
        description="Candidate application workflow"
      />
      <Status value={item.status} />
      <dl className="detail-grid">
        <div>
          <dt>Current role</dt>
          <dd>{item.current_job_title || "Not provided"}</dd>
        </div>
        <div>
          <dt>Experience</dt>
          <dd>{item.total_experience_months ?? 0} months</dd>
        </div>
        <div>
          <dt>Availability</dt>
          <dd>{item.availability_date ?? "Not provided"}</dd>
        </div>
      </dl>
      {message ? (
        <p className="form-error" role="alert">
          {message}
        </p>
      ) : null}
      {auth.can("recruitment.change_candidateapplication") ? (
        <div className="quick-actions">
          {[
            "SCREENING",
            "SHORTLISTED",
            "INTERVIEW",
            "ASSESSMENT",
            "BACKGROUND_CHECK",
            "SELECTED",
            "REJECTED",
          ].map((status) => (
            <Button
              key={status}
              className="button-secondary"
              onClick={() => void transition(status)}
            >
              {humanize(status)}
            </Button>
          ))}
        </div>
      ) : null}
      <section>
        <h2>Offers</h2>
        {offers.length ? (
          offers.map((offer) => (
            <article className="detail-card" key={offer.id}>
              <p>
                {offer.offer_number} · <Status value={offer.status} />
              </p>
              <div className="quick-actions">
                {offer.status === "DRAFT" &&
                auth.can("recruitment.change_employmentoffer") ? (
                  <Button onClick={() => void runOfferAction(offer, "submit")}>
                    Submit offer
                  </Button>
                ) : null}
                {offer.status === "SUBMITTED" &&
                auth.can("recruitment.approve_offer") ? (
                  <Button onClick={() => void runOfferAction(offer, "approve")}>
                    Approve offer
                  </Button>
                ) : null}
                {offer.status === "APPROVED" &&
                auth.can("recruitment.change_employmentoffer") ? (
                  <Button onClick={() => void runOfferAction(offer, "issue")}>
                    Issue offer
                  </Button>
                ) : null}
                {offer.status === "ISSUED" &&
                auth.can("recruitment.change_employmentoffer") ? (
                  <Button onClick={() => void runOfferAction(offer, "accept")}>
                    Record acceptance
                  </Button>
                ) : null}
                {offer.status === "ACCEPTED" &&
                auth.can("recruitment.add_onboardingcase") ? (
                  <Button
                    onClick={() =>
                      void runOfferAction(offer, "begin-onboarding")
                    }
                  >
                    Begin onboarding
                  </Button>
                ) : null}
              </div>
            </article>
          ))
        ) : (
          <p>No offer yet.</p>
        )}
      </section>
      <section>
        <h2>Onboarding</h2>
        {onboarding.length ? (
          onboarding.map((row) => (
            <article className="detail-card" key={row.id}>
              <p>
                {row.proposed_employee_number || "Employee number pending"} ·{" "}
                <Status value={row.status} />
              </p>
              <div className="quick-actions">
                {row.status === "IN_PROGRESS" &&
                auth.can("recruitment.change_onboardingcase") ? (
                  <Button
                    onClick={() =>
                      void runOnboardingAction(row, "ready-to-hire")
                    }
                  >
                    Mark ready to hire
                  </Button>
                ) : null}
                {row.status === "READY_TO_HIRE" &&
                auth.can("recruitment.hire_candidate") ? (
                  <Button onClick={() => void runOnboardingAction(row, "hire")}>
                    Convert to employee
                  </Button>
                ) : null}
                {row.status === "COMPLETED" && item.hired_employee ? (
                  <Link href={`/employees/${item.hired_employee}`}>
                    Open employee
                  </Link>
                ) : null}
              </div>
            </article>
          ))
        ) : (
          <p>Onboarding has not started.</p>
        )}
      </section>
    </>
  );
}

export function LeavePage() {
  const auth = useAuth();
  const company = selectedCompany(auth);
  const canSelf = auth.can("leave.view_own_leave_request");
  const canManage = auth.canAny(
    "leave.view_team_availability",
    "leave.approve_leave_request",
    "leave.reject_leave_request",
  );
  const [types, setTypes] = useState<LeaveType[]>([]);
  const [mine, setMine] = useState<Page<LeaveRequest> | null>(null);
  const [balances, setBalances] = useState<LeaveBalance[]>([]);
  const [manager, setManager] = useState<Page<LeaveRequest> | null>(null);
  const [team, setTeam] = useState<Page<LeaveRequest> | null>(null);
  const [holidays, setHolidays] = useState<Page<Holiday> | null>(null);
  const [values, setValues] = useState({
    leave_type: "",
    starts_at: "",
    ends_at: "",
    reason: "",
    emergency_request: false,
  });
  const [message, setMessage] = useState("");
  const [pending, setPending] = useState(false);
  const load = async () => {
    const [typeRows, myRows, balanceRows, holidayRows] = canSelf
      ? await Promise.all([
          listLeaveTypes(),
          listMyLeave(),
          listLeaveBalances(),
          listHolidays(),
        ])
      : [[], null, [], null];
    setTypes(typeRows);
    setMine(myRows);
    setBalances(balanceRows);
    setHolidays(holidayRows);
    if (canManage) {
      const [managerRows, teamRows] = await Promise.all([
        listManagerLeave(),
        listTeamLeave(),
      ]);
      setManager(managerRows);
      setTeam(teamRows);
    }
  };
  useEffect(() => {
    let current = true;
    const own = canSelf
      ? Promise.all([
          listLeaveTypes(),
          listMyLeave(),
          listLeaveBalances(),
          listHolidays(),
        ])
      : Promise.resolve([[], null, [], null] as [
          LeaveType[],
          Page<LeaveRequest> | null,
          LeaveBalance[],
          Page<Holiday> | null,
        ]);
    const managed = canManage
      ? Promise.all([listManagerLeave(), listTeamLeave()])
      : Promise.resolve([null, null] as [
          Page<LeaveRequest> | null,
          Page<LeaveRequest> | null,
        ]);
    Promise.all([own, managed])
      .then(
        ([
          [typeRows, myRows, balanceRows, holidayRows],
          [managerRows, teamRows],
        ]) => {
          if (!current) return;
          setTypes(typeRows);
          setMine(myRows);
          setBalances(balanceRows);
          setHolidays(holidayRows);
          setManager(managerRows);
          setTeam(teamRows);
        },
      )
      .catch(() => current && setMessage("Leave data could not be loaded."));
    return () => {
      current = false;
    };
  }, [company, canManage, canSelf]);
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (pending) return;
    setPending(true);
    setMessage("");
    try {
      const row = await createLeaveRequest({
        ...values,
        starts_at: new Date(values.starts_at).toISOString(),
        ends_at: new Date(values.ends_at).toISOString(),
      });
      await leaveAction("me/requests", row.id, "submit");
      setValues({
        leave_type: "",
        starts_at: "",
        ends_at: "",
        reason: "",
        emergency_request: false,
      });
      await load();
    } catch (reason) {
      setMessage(
        messageFor(reason, "The Leave request could not be submitted."),
      );
    } finally {
      setPending(false);
    }
  }
  async function decide(id: string, action: "approve" | "reject") {
    if (!window.confirm(`${humanize(action)} this Leave request?`)) return;
    try {
      await leaveAction("manager/requests", id, action, {
        reason: action === "reject" ? "Rejected after review" : "",
      });
      await load();
    } catch (reason) {
      setMessage(messageFor(reason, "The Leave decision failed."));
    }
  }
  if (!canSelf && !canManage)
    return <ErrorState message="You do not have permission to use Leave." />;
  return (
    <>
      <PageHeader
        title="Leave"
        description="Submit personal Leave and review authorized team requests."
      />
      {message ? (
        <p className="form-error" role="alert">
          {message}
        </p>
      ) : null}
      {canSelf ? (
        <>
          <section>
            <h2>Request Leave</h2>
            <form className="invoice-form" onSubmit={submit}>
              <label className="form-field">
                <span>Leave Type *</span>
                <select
                  required
                  value={values.leave_type}
                  onChange={(e) =>
                    setValues({ ...values, leave_type: e.target.value })
                  }
                >
                  <option value="">Select Leave Type</option>
                  {types.map((type) => (
                    <option key={type.id} value={type.id}>
                      {type.name}
                    </option>
                  ))}
                </select>
              </label>
              <label className="form-field">
                <span>Starts *</span>
                <input
                  required
                  type="datetime-local"
                  value={values.starts_at}
                  onChange={(e) =>
                    setValues({ ...values, starts_at: e.target.value })
                  }
                />
              </label>
              <label className="form-field">
                <span>Ends *</span>
                <input
                  required
                  type="datetime-local"
                  value={values.ends_at}
                  onChange={(e) =>
                    setValues({ ...values, ends_at: e.target.value })
                  }
                />
              </label>
              <label className="form-field">
                <span>Reason *</span>
                <textarea
                  required
                  value={values.reason}
                  onChange={(e) =>
                    setValues({ ...values, reason: e.target.value })
                  }
                />
              </label>
              <Button disabled={pending}>
                {pending ? "Submitting..." : "Submit Leave request"}
              </Button>
            </form>
          </section>
          <section>
            <h2>My balances</h2>
            {balances.length ? (
              <div className="table-wrap">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Leave Type</th>
                      <th>Entitled</th>
                      <th>Reserved</th>
                      <th>Taken</th>
                      <th>Available</th>
                    </tr>
                  </thead>
                  <tbody>
                    {balances.map((row) => (
                      <tr key={row.leave_type}>
                        <td>{row.leave_type_name}</td>
                        <td>{row.entitled}</td>
                        <td>{row.reserved}</td>
                        <td>{row.taken}</td>
                        <td>
                          {row.available} {humanize(row.unit)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <p>No balance ledger entries.</p>
            )}
          </section>
          <section>
            <h2>My requests</h2>
            {mine ? (
              <LeaveTable rows={mine.results} />
            ) : (
              <LoadingState label="Loading Leave requests..." />
            )}
          </section>
          <section>
            <h2>Company holidays</h2>
            {holidays?.results.length ? (
              <ul className="setup-list">
                {holidays.results.map((holiday) => (
                  <li key={holiday.id}>
                    {holiday.date} · {holiday.name}
                  </li>
                ))}
              </ul>
            ) : (
              <p>No upcoming holidays configured.</p>
            )}
          </section>
        </>
      ) : null}
      {canManage ? (
        <>
          <section>
            <h2>Manager approval inbox</h2>
            {manager ? (
              <LeaveTable
                rows={manager.results}
                actions={(row) => (
                  <>
                    {auth.can("leave.approve_leave_request") ? (
                      <Button onClick={() => void decide(row.id, "approve")}>
                        Approve
                      </Button>
                    ) : null}
                    {auth.can("leave.reject_leave_request") ? (
                      <Button
                        className="button-secondary"
                        onClick={() => void decide(row.id, "reject")}
                      >
                        Reject
                      </Button>
                    ) : null}
                  </>
                )}
              />
            ) : (
              <LoadingState label="Loading approval inbox..." />
            )}
          </section>
          <section>
            <h2>Team Leave calendar</h2>
            {team ? (
              <LeaveTable rows={team.results} />
            ) : (
              <LoadingState label="Loading team Leave..." />
            )}
          </section>
        </>
      ) : null}
    </>
  );
}

function LeaveTable({
  rows,
  actions,
}: {
  rows: LeaveRequest[];
  actions?: (row: LeaveRequest) => ReactNode;
}) {
  if (!rows.length)
    return <EmptyState message="No Leave requests in this view." />;
  return (
    <div className="table-wrap">
      <table className="data-table">
        <thead>
          <tr>
            <th>Request</th>
            <th>Employee</th>
            <th>Leave Type</th>
            <th>Dates</th>
            <th>Status</th>
            {actions ? <th>Actions</th> : null}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.id}>
              <td>{row.request_number}</td>
              <td>{row.employee_name ?? "My request"}</td>
              <td>{row.leave_type_name ?? row.leave_type}</td>
              <td>
                {new Date(row.starts_at).toLocaleDateString()} –{" "}
                {new Date(row.ends_at).toLocaleDateString()}
              </td>
              <td>
                <Status value={row.status} />
              </td>
              {actions ? (
                <td>
                  <div className="quick-actions">{actions(row)}</div>
                </td>
              ) : null}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function LearningPage({
  searchParams,
}: {
  searchParams: Record<string, string>;
}) {
  const auth = useAuth();
  const company = selectedCompany(auth);
  const canCourses = auth.can("training.view_trainingcourse");
  const [courses, setCourses] = useState<Page<Course> | null>(null);
  const [sessions, setSessions] = useState<Page<LearningSession> | null>(null);
  const [qualifications, setQualifications] =
    useState<Page<Qualification> | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    if (!canCourses) return;
    let current = true;
    Promise.all([
      listCourses(searchParams),
      listSessions({ ordering: "start_datetime" }),
      listQualifications(),
    ])
      .then(([courseRows, sessionRows, qualificationRows]) => {
        if (current) {
          setCourses(courseRows);
          setSessions(sessionRows);
          setQualifications(qualificationRows);
        }
      })
      .catch(
        () =>
          current && setError("Learning & Qualifications could not be loaded."),
      );
    return () => {
      current = false;
    };
  }, [canCourses, company, searchParams]);
  if (!canCourses)
    return (
      <ErrorState message="You do not have permission to view Learning & Qualifications." />
    );
  return (
    <>
      <PageHeader
        title="Learning & Qualifications"
        description="Courses, sessions, participation, and employee qualifications."
        actions={
          auth.can("training.add_trainingcourse") ? (
            <Link className="button" href="/learning/courses/new">
              Create course
            </Link>
          ) : undefined
        }
      />
      <WorkspaceTabs>
        {auth.can("training.add_trainingsession") ? (
          <Link href="/learning/sessions/new">Create session</Link>
        ) : null}
      </WorkspaceTabs>
      <form className="invoice-filters" action="/learning">
        <label>
          Search
          <input
            name="search"
            defaultValue={searchParams.search}
            placeholder="Course code or title"
          />
        </label>
        <label>
          Status
          <select name="status" defaultValue={searchParams.status}>
            <option value="">All</option>
            <option>DRAFT</option>
            <option>ACTIVE</option>
            <option>RETIRED</option>
          </select>
        </label>
        <Button>Filter</Button>
      </form>
      {error ? (
        <ErrorState message={error} />
      ) : !courses || !sessions || !qualifications ? (
        <LoadingState label="Loading Learning & Qualifications..." />
      ) : (
        <div className="dashboard-grid">
          <section className="dashboard-widget">
            <h2>Course catalog</h2>
            {courses.results.length ? (
              <ul className="setup-list">
                {courses.results.map((course) => (
                  <li key={course.id}>
                    <Link href={`/learning/courses/${course.id}`}>
                      {course.code} · {course.title}
                    </Link>{" "}
                    <Status value={course.status} />
                  </li>
                ))}
              </ul>
            ) : (
              <EmptyState message="No courses match this filter." />
            )}
          </section>
          <section className="dashboard-widget">
            <h2>Sessions</h2>
            {sessions.results.length ? (
              <ul className="setup-list">
                {sessions.results.map((session) => (
                  <li key={session.id}>
                    <Link href={`/learning/sessions/${session.id}`}>
                      {session.session_number}
                    </Link>{" "}
                    · {new Date(session.start_datetime).toLocaleDateString()}{" "}
                    <Status value={session.status} />
                  </li>
                ))}
              </ul>
            ) : (
              <p>No sessions scheduled.</p>
            )}
          </section>
          <section className="dashboard-widget">
            <h2>Qualifications</h2>
            <p>
              {qualifications.count} employee qualification records in this
              Company.
            </p>
          </section>
        </div>
      )}
    </>
  );
}

function CourseForm({ item }: { item?: Course }) {
  const auth = useAuth();
  const router = useRouter();
  const [values, setValues] = useState({
    code: item?.code ?? "",
    title: item?.title ?? "",
    description: item?.description ?? "",
    objective: item?.objective ?? "",
    delivery_method: item?.delivery_method ?? "CLASSROOM",
    duration_hours: item?.duration_hours ?? "1.00",
    minimum_pass_percentage: "0.00",
    minimum_attendance_percentage: "0.00",
    requires_assessment: item?.requires_assessment ?? false,
    produces_certificate: item?.produces_certificate ?? false,
  });
  const [message, setMessage] = useState("");
  const [pending, setPending] = useState(false);
  if (
    !auth.can(
      item ? "training.change_trainingcourse" : "training.add_trainingcourse",
    )
  )
    return (
      <ErrorState message="You do not have permission to manage courses." />
    );
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (pending) return;
    setPending(true);
    try {
      const saved = await saveCourse(item?.id ?? null, values);
      router.push(`/learning/courses/${saved.id}`);
    } catch (reason) {
      setMessage(messageFor(reason, "The course could not be saved."));
    } finally {
      setPending(false);
    }
  }
  return (
    <form className="invoice-form" onSubmit={submit}>
      {message ? (
        <p className="form-error" role="alert">
          {message}
        </p>
      ) : null}
      <label className="form-field">
        <span>Code *</span>
        <input
          required
          value={values.code}
          onChange={(e) => setValues({ ...values, code: e.target.value })}
        />
      </label>
      <label className="form-field">
        <span>Title *</span>
        <input
          required
          value={values.title}
          onChange={(e) => setValues({ ...values, title: e.target.value })}
        />
      </label>
      <label className="form-field">
        <span>Description</span>
        <textarea
          value={values.description}
          onChange={(e) =>
            setValues({ ...values, description: e.target.value })
          }
        />
      </label>
      <label className="form-field">
        <span>Objective</span>
        <textarea
          value={values.objective}
          onChange={(e) => setValues({ ...values, objective: e.target.value })}
        />
      </label>
      <label className="form-field">
        <span>Delivery method *</span>
        <select
          value={values.delivery_method}
          onChange={(e) =>
            setValues({ ...values, delivery_method: e.target.value })
          }
        >
          <option>CLASSROOM</option>
          <option>ONLINE</option>
          <option>BLENDED</option>
          <option>ON_THE_JOB</option>
        </select>
      </label>
      <label className="form-field">
        <span>Duration hours *</span>
        <input
          required
          type="number"
          step="0.25"
          min="0.25"
          value={values.duration_hours}
          onChange={(e) =>
            setValues({ ...values, duration_hours: e.target.value })
          }
        />
      </label>
      <div className="form-actions">
        <Button disabled={pending}>
          {pending ? "Saving..." : "Save course"}
        </Button>
        <Link className="button button-secondary" href="/learning">
          Cancel
        </Link>
      </div>
    </form>
  );
}
export function CourseCreatePage() {
  return (
    <>
      <PageHeader
        title="Create course"
        description="Add a generic Company learning course."
      />
      <CourseForm />
    </>
  );
}
export function CourseDetailPage({ id }: { id: string }) {
  const auth = useAuth();
  const company = selectedCompany(auth);
  const [item, setItem] = useState<Course | null>(null);
  const [message, setMessage] = useState("");
  useEffect(() => {
    void getCourse(id)
      .then(setItem)
      .catch(() => setMessage("The course could not be loaded."));
  }, [company, id]);
  async function act(action: "activate" | "retire") {
    try {
      setItem(await learningAction<Course>("courses", id, action));
    } catch (reason) {
      setMessage(messageFor(reason, "The course action failed."));
    }
  }
  if (message && !item) return <ErrorState message={message} />;
  if (!item) return <LoadingState label="Loading course..." />;
  return (
    <>
      <PageHeader
        title={item.title}
        description={`${item.code} · ${humanize(item.delivery_method)}`}
      />
      <Status value={item.status} />
      <p>{item.description || "No description."}</p>
      {message ? (
        <p className="form-error" role="alert">
          {message}
        </p>
      ) : null}
      {auth.can("training.change_trainingcourse") ? (
        <div className="quick-actions">
          {item.status === "DRAFT" ? (
            <Button onClick={() => void act("activate")}>
              Activate course
            </Button>
          ) : null}
          {item.status === "ACTIVE" ? (
            <Button
              className="button-secondary"
              onClick={() => void act("retire")}
            >
              Retire course
            </Button>
          ) : null}
        </div>
      ) : null}
    </>
  );
}

function SessionForm() {
  const auth = useAuth();
  const router = useRouter();
  const company = selectedCompany(auth);
  const [courses, setCourses] = useState<Course[]>([]);
  const [versions, setVersions] = useState<CourseVersion[]>([]);
  const [values, setValues] = useState({
    course: "",
    course_version: "",
    start_datetime: "",
    end_datetime: "",
    enrollment_deadline: "",
    capacity: "1",
    notes: "",
  });
  const [message, setMessage] = useState("");
  const [pending, setPending] = useState(false);
  useEffect(() => {
    void listCourses({ status: "ACTIVE" }).then((v) => setCourses(v.results));
  }, [company]);
  useEffect(() => {
    if (!values.course) return;
    let current = true;
    listCourseVersions(values.course)
      .then((rows) => {
        if (!current) return;
        setVersions(rows);
        const currentVersion = rows.find((row) => row.is_current);
        if (currentVersion)
          setValues((value) => ({
            ...value,
            course_version: currentVersion.id,
          }));
      })
      .catch(
        () => current && setMessage("Course versions could not be loaded."),
      );
    return () => {
      current = false;
    };
  }, [values.course]);
  if (!auth.can("training.add_trainingsession"))
    return (
      <ErrorState message="You do not have permission to create Learning sessions." />
    );
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (pending) return;
    setPending(true);
    try {
      const saved = await saveSession(null, {
        ...values,
        start_datetime: new Date(values.start_datetime).toISOString(),
        end_datetime: new Date(values.end_datetime).toISOString(),
        enrollment_deadline: values.enrollment_deadline
          ? new Date(values.enrollment_deadline).toISOString()
          : null,
        capacity: Number(values.capacity),
      });
      router.push(`/learning/sessions/${saved.id}`);
    } catch (reason) {
      setMessage(
        messageFor(
          reason,
          "The session could not be saved. Select a current course version.",
        ),
      );
    } finally {
      setPending(false);
    }
  }
  return (
    <form className="invoice-form" onSubmit={submit}>
      {message ? (
        <p className="form-error" role="alert">
          {message}
        </p>
      ) : null}
      <label className="form-field">
        <span>Course *</span>
        <select
          required
          value={values.course}
          onChange={(e) => setValues({ ...values, course: e.target.value })}
        >
          <option value="">Select course</option>
          {courses.map((course) => (
            <option key={course.id} value={course.id}>
              {course.code} · {course.title}
            </option>
          ))}
        </select>
      </label>
      <label className="form-field">
        <span>Course version *</span>
        <select
          required
          value={values.course_version}
          onChange={(e) =>
            setValues({ ...values, course_version: e.target.value })
          }
        >
          <option value="">Select current version</option>
          {versions.map((version) => (
            <option key={version.id} value={version.id}>
              Version {version.version_number}
              {version.is_current ? " (current)" : ""}
            </option>
          ))}
        </select>
      </label>
      <label className="form-field">
        <span>Starts *</span>
        <input
          required
          type="datetime-local"
          value={values.start_datetime}
          onChange={(e) =>
            setValues({ ...values, start_datetime: e.target.value })
          }
        />
      </label>
      <label className="form-field">
        <span>Ends *</span>
        <input
          required
          type="datetime-local"
          value={values.end_datetime}
          onChange={(e) =>
            setValues({ ...values, end_datetime: e.target.value })
          }
        />
      </label>
      <label className="form-field">
        <span>Capacity *</span>
        <input
          required
          min="1"
          type="number"
          value={values.capacity}
          onChange={(e) => setValues({ ...values, capacity: e.target.value })}
        />
      </label>
      <label className="form-field">
        <span>Notes</span>
        <textarea
          value={values.notes}
          onChange={(e) => setValues({ ...values, notes: e.target.value })}
        />
      </label>
      <div className="form-actions">
        <Button disabled={pending}>
          {pending ? "Saving..." : "Save session"}
        </Button>
        <Link className="button button-secondary" href="/learning">
          Cancel
        </Link>
      </div>
    </form>
  );
}
export function SessionCreatePage() {
  return (
    <>
      <PageHeader
        title="Create Learning session"
        description="Schedule delivery for an active course version."
      />
      <SessionForm />
    </>
  );
}
export function SessionDetailPage({ id }: { id: string }) {
  const auth = useAuth();
  const company = selectedCompany(auth);
  const [item, setItem] = useState<LearningSession | null>(null);
  const [employee, setEmployee] = useState("");
  const [message, setMessage] = useState("");
  useEffect(() => {
    void getSession(id)
      .then(setItem)
      .catch(() => setMessage("The Learning session could not be loaded."));
  }, [company, id]);
  async function act(action: string, body = {}) {
    try {
      if (action === "enroll") {
        await learningAction("sessions", id, action, body);
        setEmployee("");
      } else
        setItem(
          await learningAction<LearningSession>("sessions", id, action, body),
        );
    } catch (reason) {
      setMessage(messageFor(reason, "The session action failed."));
    }
  }
  if (message && !item) return <ErrorState message={message} />;
  if (!item) return <LoadingState label="Loading Learning session..." />;
  return (
    <>
      <PageHeader
        title={item.session_number}
        description={`${new Date(item.start_datetime).toLocaleString()} – ${new Date(item.end_datetime).toLocaleString()}`}
      />
      <Status value={item.status} />
      {message ? (
        <p className="form-error" role="alert">
          {message}
        </p>
      ) : null}
      {auth.can("training.change_trainingsession") ? (
        <div className="quick-actions">
          {item.status === "DRAFT" ? (
            <Button onClick={() => void act("schedule")}>Schedule</Button>
          ) : null}
          {item.status === "SCHEDULED" ? (
            <>
              <Button onClick={() => void act("open-enrollment")}>
                Open enrollment
              </Button>
              <Button
                className="button-secondary"
                onClick={() => void act("start")}
              >
                Start
              </Button>
            </>
          ) : null}
          {item.status === "OPEN_FOR_ENROLLMENT" ? (
            <Button onClick={() => void act("start")}>Start</Button>
          ) : null}
          {item.status === "IN_PROGRESS" ? (
            <Button onClick={() => void act("complete")}>Complete</Button>
          ) : null}
        </div>
      ) : null}
      {auth.can("training.add_trainingenrollment") ? (
        <form
          className="invoice-form"
          onSubmit={(event) => {
            event.preventDefault();
            void act("enroll", { employee, allow_waitlist: true });
          }}
        >
          <h2>Enroll employee</h2>
          <label className="form-field">
            <span>Employee ID *</span>
            <input
              required
              value={employee}
              onChange={(e) => setEmployee(e.target.value)}
            />
          </label>
          <Button>Enroll</Button>
        </form>
      ) : null}
    </>
  );
}

export function EmployeeQualificationSummary({
  employeeId,
}: {
  employeeId: string;
}) {
  const auth = useAuth();
  const enabled =
    auth.hasModule("learning") &&
    auth.can("training.view_employeequalification");
  const company = selectedCompany(auth);
  const [rows, setRows] = useState<Qualification[]>([]);
  const [types, setTypes] = useState<QualificationType[]>([]);
  useEffect(() => {
    if (!enabled) return;
    let current = true;
    Promise.all([
      listQualifications(employeeId),
      listQualificationTypes(),
    ]).then(([qualificationRows, typeRows]) => {
      if (current) {
        setRows(qualificationRows.results);
        setTypes(typeRows);
      }
    });
    return () => {
      current = false;
    };
  }, [company, employeeId, enabled]);
  if (!enabled) return null;
  const names = new Map(types.map((type) => [type.id, type.name]));
  return (
    <section>
      <h2>Learning & Qualifications</h2>
      {rows.length ? (
        <div className="table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>Qualification</th>
                <th>Obtained</th>
                <th>Expires</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.id}>
                  <td>
                    {names.get(row.qualification_type) ?? "Qualification"}
                  </td>
                  <td>{row.obtained_on}</td>
                  <td>{row.expires_on ?? "No expiry"}</td>
                  <td>
                    <Status value={row.status} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p>No qualifications recorded.</p>
      )}
    </section>
  );
}
