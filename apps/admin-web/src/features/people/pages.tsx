"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type FormEvent,
} from "react";

import { PageHeader } from "@/components/layout/page-header";
import { Button } from "@/components/ui/button";
import { FormError, FormField } from "@/components/ui/form-field";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/states";
import { useAuth } from "@/features/auth/auth-context";
import { ApiError } from "@/lib/api/client";
import {
  createEmployee,
  employeeAction,
  getEmployee,
  listAddresses,
  listAssignmentHistory,
  listEmergencyContacts,
  listEmployeeDocuments,
  listEmployees,
  listReferences,
  listStatusHistory,
  saveAddress,
  saveEmergencyContact,
  updateEmployee,
} from "./api";
import type {
  AssignmentHistory,
  EmergencyContact,
  Employee,
  EmployeeAddress,
  EmployeeDocument,
  OrganizationReference,
  StatusHistory,
} from "./types";

const humanize = (value?: string | null) =>
  value
    ? value
        .replaceAll("_", " ")
        .toLowerCase()
        .replace(/^./, (c) => c.toUpperCase())
    : "-";
const today = () => new Date().toISOString().slice(0, 10);

const employeeTypeLabel = (value: string, securityOperations: boolean) =>
  value === "SECURITY_GUARD" && !securityOperations
    ? "Existing employee classification"
    : humanize(value);

function Status({ value }: { value: string }) {
  return (
    <span className={`status-badge status-${value.toLowerCase()}`}>
      {humanize(value)}
    </span>
  );
}

export function EmployeeListPage({
  searchParams,
}: {
  searchParams: Record<string, string>;
}) {
  const auth = useAuth();
  const companyId = auth.company_context.selected_company?.id;
  const [data, setData] = useState<Awaited<
    ReturnType<typeof listEmployees>
  > | null>(null);
  const [loadedFor, setLoadedFor] = useState<string | null>(null);
  const [references, setReferences] = useState<
    Record<string, OrganizationReference[]>
  >({});
  const [error, setError] = useState("");
  const [errorFor, setErrorFor] = useState<string | null>(null);
  useEffect(() => {
    if (!companyId || !auth.can("workforce.view_employee")) return;
    let current = true;
    Promise.all([
      listEmployees(searchParams),
      listReferences("branches"),
      listReferences("departments"),
    ])
      .then(([employees, branches, departments]) => {
        if (current) {
          setData(employees);
          setLoadedFor(companyId);
          setError("");
          setReferences({ branches, departments });
        }
      })
      .catch(() => {
        if (current) {
          setErrorFor(companyId);
          setError("Employees could not be loaded.");
        }
      });
    return () => {
      current = false;
    };
  }, [auth, companyId, searchParams]);
  if (!auth.can("workforce.view_employee"))
    return (
      <ErrorState message="You do not have permission to view employees." />
    );
  const visibleData = loadedFor === companyId ? data : null;
  const visibleError = errorFor === companyId ? error : "";
  return (
    <>
      <PageHeader
        title="Employees"
        description="Manage people, employment details, and Company assignments."
        actions={
          auth.can("workforce.add_employee") ? (
            <Link className="button" href="/employees/new">
              Add employee
            </Link>
          ) : undefined
        }
      />
      <form className="invoice-filters" action="/employees">
        <label>
          Search
          <input
            name="search"
            defaultValue={searchParams.search}
            placeholder="Name, employee number, email, or phone"
          />
        </label>
        <label>
          Status
          <select
            name="employment_status"
            defaultValue={searchParams.employment_status}
          >
            <option value="">All statuses</option>
            {[
              "DRAFT",
              "ACTIVE",
              "ON_LEAVE",
              "SUSPENDED",
              "RESIGNED",
              "TERMINATED",
              "RETIRED",
              "ABSCONDED",
            ].map((v) => (
              <option key={v} value={v}>
                {humanize(v)}
              </option>
            ))}
          </select>
        </label>
        <label>
          Branch
          <select name="branch" defaultValue={searchParams.branch}>
            <option value="">All branches</option>
            {references.branches?.map((v) => (
              <option key={v.id} value={v.id}>
                {v.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          Department
          <select name="department" defaultValue={searchParams.department}>
            <option value="">All departments</option>
            {references.departments?.map((v) => (
              <option key={v.id} value={v.id}>
                {v.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          Order
          <select
            name="ordering"
            defaultValue={searchParams.ordering || "employee_number"}
          >
            <option value="employee_number">Employee number</option>
            <option value="first_name">First name</option>
            <option value="joining_date">Joining date</option>
            <option value="-joining_date">Newest joiners</option>
          </select>
        </label>
        <div className="filter-actions">
          <Button type="submit">Apply</Button>
          <Link className="button button-secondary" href="/employees">
            Clear
          </Link>
        </div>
      </form>
      {visibleError ? (
        <ErrorState message={visibleError} />
      ) : !visibleData ? (
        <LoadingState label="Loading employees..." />
      ) : !visibleData.results.length ? (
        <EmptyState
          message="No employees yet."
          action={
            auth.can("workforce.add_employee") ? (
              <Link className="button" href="/employees/new">
                Add employee
              </Link>
            ) : undefined
          }
        />
      ) : (
        <>
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Employee</th>
                  <th>Employment</th>
                  <th>Branch</th>
                  <th>Department</th>
                  <th>Designation</th>
                  <th>Type</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {visibleData.results.map((employee) => (
                  <tr key={employee.id}>
                    <td>
                      <Link href={`/employees/${employee.id}`}>
                        {employee.full_name}
                      </Link>
                      <small className="table-secondary">
                        {employee.employee_number}
                      </small>
                    </td>
                    <td>
                      <Status value={employee.employment_status} />
                    </td>
                    <td>{employee.branch_name || "-"}</td>
                    <td>{employee.department_name || "-"}</td>
                    <td>{employee.designation_name || "-"}</td>
                    <td>
                      {employeeTypeLabel(
                        employee.employee_type,
                        auth.hasModule("security_operations"),
                      )}
                    </td>
                    <td>
                      {auth.can("workforce.change_employee") ? (
                        <Link href={`/employees/${employee.id}/edit`}>
                          Edit
                        </Link>
                      ) : (
                        "-"
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <nav className="pagination" aria-label="Employee pages">
            {visibleData.previous ? (
              <Link
                href={{
                  pathname: "/employees",
                  query: {
                    ...searchParams,
                    page: Math.max(1, Number(searchParams.page || 1) - 1),
                  },
                }}
              >
                Previous
              </Link>
            ) : (
              <span />
            )}
            <span>{visibleData.count} employees</span>
            {visibleData.next ? (
              <Link
                href={{
                  pathname: "/employees",
                  query: {
                    ...searchParams,
                    page: Number(searchParams.page || 1) + 1,
                  },
                }}
              >
                Next
              </Link>
            ) : (
              <span />
            )}
          </nav>
        </>
      )}
    </>
  );
}

const blankEmployee = {
  employee_number: "",
  first_name: "",
  middle_name: "",
  last_name: "",
  preferred_name: "",
  gender: "UNSPECIFIED",
  date_of_birth: "",
  marital_status: "UNSPECIFIED",
  nationality: "PK",
  personal_email: "",
  mobile_number: "",
  alternate_mobile_number: "",
  employee_type: "OFFICE_STAFF",
  employment_type: "PERMANENT",
  joining_date: today(),
  confirmation_date: "",
  probation_end_date: "",
  branch: "",
  department: "",
  designation: "",
};

function EmployeeForm({ employee }: { employee?: Employee }) {
  const auth = useAuth();
  const router = useRouter();
  const [values, setValues] = useState({
    ...blankEmployee,
    ...(employee
      ? Object.fromEntries(
          Object.keys(blankEmployee).map((key) => [
            key,
            String(employee[key as keyof Employee] ?? ""),
          ]),
        )
      : {}),
  });
  const [refs, setRefs] = useState<Record<string, OrganizationReference[]>>({});
  const [errors, setErrors] = useState<Record<string, string[]>>({});
  const [message, setMessage] = useState("");
  const [pending, setPending] = useState(false);
  useEffect(() => {
    Promise.all([
      listReferences("branches"),
      listReferences("departments"),
      listReferences("designations"),
    ])
      .then(([branches, departments, designations]) =>
        setRefs({ branches, departments, designations }),
      )
      .catch(() => setMessage("Organization references could not be loaded."));
  }, []);
  const permission = employee
    ? "workforce.change_employee"
    : "workforce.add_employee";
  if (!auth.can(permission))
    return (
      <ErrorState message="You do not have permission to manage this employee." />
    );
  const set = (field: string, value: string) =>
    setValues((current) => ({ ...current, [field]: value }));
  async function submit(event: FormEvent) {
    event.preventDefault();
    setPending(true);
    setErrors({});
    setMessage("");
    const payload = Object.fromEntries(
      Object.entries(values).filter(([, value]) => value !== ""),
    );
    if (employee)
      for (const field of [
        "employee_number",
        "branch",
        "department",
        "designation",
      ])
        delete payload[field];
    if (
      employee?.employee_type === "SECURITY_GUARD" &&
      !auth.hasModule("security_operations")
    )
      delete payload.employee_type;
    try {
      const saved = employee
        ? await updateEmployee(employee.id, payload)
        : await createEmployee(payload);
      router.push(`/employees/${saved.id}`);
    } catch (reason) {
      if (reason instanceof ApiError) {
        setErrors(reason.fieldErrors);
        setMessage(reason.message);
      } else setMessage("The employee could not be saved.");
    } finally {
      setPending(false);
    }
  }
  const employeeTypes = [
    "MANAGEMENT",
    "OFFICE_STAFF",
    "CONTROL_ROOM",
    "SUPERVISOR",
    "DRIVER",
    "TRAINER",
    "OTHER",
    ...(auth.hasModule("security_operations") ? ["SECURITY_GUARD"] : []),
  ];
  return (
    <form
      className="invoice-form"
      aria-label={employee ? "Edit employee" : "Add employee"}
      onSubmit={submit}
    >
      <fieldset>
        <legend>Identity</legend>
        <FormField
          id="employee_number"
          label="Employee number"
          required
          disabled={Boolean(employee)}
          value={values.employee_number}
          onChange={(e) => set("employee_number", e.target.value)}
          error={errors.employee_number?.[0]}
        />
        <FormField
          id="first_name"
          label="First name"
          required
          value={values.first_name}
          onChange={(e) => set("first_name", e.target.value)}
          error={errors.first_name?.[0]}
        />
        <FormField
          id="middle_name"
          label="Middle name"
          value={values.middle_name}
          onChange={(e) => set("middle_name", e.target.value)}
        />
        <FormField
          id="last_name"
          label="Last name"
          value={values.last_name}
          onChange={(e) => set("last_name", e.target.value)}
        />
        <FormField
          id="preferred_name"
          label="Preferred name"
          value={values.preferred_name}
          onChange={(e) => set("preferred_name", e.target.value)}
        />
        <FormField
          id="date_of_birth"
          label="Date of birth"
          type="date"
          value={values.date_of_birth}
          onChange={(e) => set("date_of_birth", e.target.value)}
        />
      </fieldset>
      <fieldset>
        <legend>Contact</legend>
        <FormField
          id="personal_email"
          label="Personal email"
          type="email"
          value={values.personal_email}
          onChange={(e) => set("personal_email", e.target.value)}
        />
        <FormField
          id="mobile_number"
          label="Mobile number"
          required
          value={values.mobile_number}
          onChange={(e) => set("mobile_number", e.target.value)}
          error={errors.mobile_number?.[0]}
        />
        <FormField
          id="alternate_mobile_number"
          label="Alternate mobile"
          value={values.alternate_mobile_number}
          onChange={(e) => set("alternate_mobile_number", e.target.value)}
        />
      </fieldset>
      <fieldset>
        <legend>Employment</legend>
        {employee?.employee_type === "SECURITY_GUARD" &&
        !auth.hasModule("security_operations") ? (
          <p className="help-text">
            Existing employee classification is retained. Enable the relevant
            Company module to change it.
          </p>
        ) : (
          <label className="form-field">
            <span>Employee type</span>
            <select
              value={values.employee_type}
              onChange={(e) => set("employee_type", e.target.value)}
            >
              {employeeTypes.map((v) => (
                <option key={v} value={v}>
                  {humanize(v)}
                </option>
              ))}
            </select>
          </label>
        )}
        <label className="form-field">
          <span>Employment type</span>
          <select
            value={values.employment_type}
            onChange={(e) => set("employment_type", e.target.value)}
          >
            {[
              "PERMANENT",
              "CONTRACT",
              "TEMPORARY",
              "PROBATION",
              "DAILY_WAGE",
            ].map((v) => (
              <option key={v} value={v}>
                {humanize(v)}
              </option>
            ))}
          </select>
        </label>
        <FormField
          id="joining_date"
          label="Joining date"
          type="date"
          required
          value={values.joining_date}
          onChange={(e) => set("joining_date", e.target.value)}
        />
      </fieldset>
      {!employee ? (
        <fieldset>
          <legend>Organization assignment</legend>
          {(["branches", "departments", "designations"] as const).map(
            (kind) => {
              const field = kind.slice(0, -2);
              return (
                <label className="form-field" key={kind}>
                  <span>{humanize(field)}</span>
                  <select
                    value={values[field as keyof typeof values]}
                    onChange={(e) => set(field, e.target.value)}
                  >
                    <option value="">Unassigned</option>
                    {refs[kind]?.map((value) => (
                      <option key={value.id} value={value.id}>
                        {value.name}
                      </option>
                    ))}
                  </select>
                </label>
              );
            },
          )}
        </fieldset>
      ) : null}
      <FormError message={message} />
      <div className="filter-actions">
        <Button disabled={pending}>
          {pending ? "Saving..." : "Save employee"}
        </Button>
        <Link
          className="button button-secondary"
          href={employee ? `/employees/${employee.id}` : "/employees"}
        >
          Cancel
        </Link>
      </div>
    </form>
  );
}

export function EmployeeCreatePage() {
  return (
    <>
      <PageHeader
        title="Add employee"
        description="Create a Company employee record."
      />
      <EmployeeForm />
    </>
  );
}
export function EmployeeEditPage({ id }: { id: string }) {
  const auth = useAuth();
  const companyId = auth.company_context.selected_company?.id;
  const [employee, setEmployee] = useState<Employee | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    let current = true;
    getEmployee(id)
      .then((value) => current && setEmployee(value))
      .catch(
        (reason) =>
          current &&
          setError(
            reason instanceof ApiError && reason.status === 404
              ? "Employee not found."
              : "Employee could not be loaded.",
          ),
      );
    return () => {
      current = false;
    };
  }, [companyId, id]);
  return error ? (
    <ErrorState message={error} />
  ) : !employee || employee.company !== companyId ? (
    <LoadingState label="Loading employee..." />
  ) : (
    <>
      <PageHeader
        title={`Edit ${employee.full_name}`}
        description={employee.employee_number}
      />
      <EmployeeForm employee={employee} />
    </>
  );
}

function RelatedPeopleData({
  employee,
  reloadEmployee,
}: {
  employee: Employee;
  reloadEmployee: () => void;
}) {
  const auth = useAuth();
  const [addresses, setAddresses] = useState<EmployeeAddress[]>([]);
  const [contacts, setContacts] = useState<EmergencyContact[]>([]);
  const [statuses, setStatuses] = useState<StatusHistory[]>([]);
  const [assignments, setAssignments] = useState<AssignmentHistory[]>([]);
  const [documents, setDocuments] = useState<EmployeeDocument[]>([]);
  const [references, setReferences] = useState<
    Record<string, OrganizationReference[]>
  >({});
  const [message, setMessage] = useState("");
  const load = useCallback(
    () =>
      Promise.allSettled([
        listAddresses(employee.id),
        listEmergencyContacts(employee.id),
        listStatusHistory(employee.id),
        listAssignmentHistory(employee.id),
        listEmployeeDocuments(employee.id),
      ]).then(([a, c, s, h, d]) => {
        if (a.status === "fulfilled") setAddresses(a.value);
        if (c.status === "fulfilled") setContacts(c.value);
        if (s.status === "fulfilled") setStatuses(s.value);
        if (h.status === "fulfilled") setAssignments(h.value);
        if (d.status === "fulfilled") setDocuments(d.value);
      }),
    [employee.id],
  );
  useEffect(() => {
    void load();
    Promise.all([
      listReferences("branches"),
      listReferences("departments"),
      listReferences("designations"),
    ])
      .then(([branches, departments, designations]) =>
        setReferences({ branches, departments, designations }),
      )
      .catch(() => undefined);
  }, [employee.id, load]);
  async function addAddress(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    try {
      await saveAddress(employee.id, null, Object.fromEntries(data));
      event.currentTarget.reset();
      await load();
    } catch (reason) {
      setMessage(
        reason instanceof ApiError
          ? reason.message
          : "Address could not be saved.",
      );
    }
  }
  async function addContact(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    try {
      await saveEmergencyContact(employee.id, null, Object.fromEntries(data));
      event.currentTarget.reset();
      await load();
    } catch (reason) {
      setMessage(
        reason instanceof ApiError
          ? reason.message
          : "Emergency contact could not be saved.",
      );
    }
  }
  async function editAddress(
    event: FormEvent<HTMLFormElement>,
    addressId: string,
  ) {
    event.preventDefault();
    try {
      await saveAddress(
        employee.id,
        addressId,
        Object.fromEntries(new FormData(event.currentTarget)),
      );
      await load();
    } catch (reason) {
      setMessage(
        reason instanceof ApiError
          ? reason.message
          : "Address could not be updated.",
      );
    }
  }
  async function editContact(
    event: FormEvent<HTMLFormElement>,
    contactId: string,
  ) {
    event.preventDefault();
    try {
      await saveEmergencyContact(
        employee.id,
        contactId,
        Object.fromEntries(new FormData(event.currentTarget)),
      );
      await load();
    } catch (reason) {
      setMessage(
        reason instanceof ApiError
          ? reason.message
          : "Emergency contact could not be updated.",
      );
    }
  }
  async function changeAssignment(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    try {
      await employeeAction(employee.id, "change-assignment", {
        ...Object.fromEntries(new FormData(event.currentTarget)),
        effective_from: today(),
      });
      reloadEmployee();
      await load();
    } catch (reason) {
      setMessage(
        reason instanceof ApiError
          ? reason.message
          : "Organization assignment could not be updated.",
      );
    }
  }
  async function transition(action: string, terminal = false) {
    if (
      !window.confirm(`Confirm ${humanize(action)} for ${employee.full_name}?`)
    )
      return;
    try {
      await employeeAction(employee.id, action, {
        effective_date: today(),
        ...(terminal ? { exit_date: today() } : {}),
        reason: "Updated from the People workspace",
      });
      reloadEmployee();
      await load();
    } catch (reason) {
      setMessage(
        reason instanceof ApiError
          ? reason.message
          : "Employment status could not be updated.",
      );
    }
  }
  return (
    <div className="workspace-sections">
      <FormError message={message} />
      {auth.can("workforce.manage_employee_status") ? (
        <section className="detail-card">
          <h2>Employment actions</h2>
          <div className="quick-actions">
            {employee.employment_status === "DRAFT" ? (
              <Button type="button" onClick={() => transition("activate")}>
                Activate
              </Button>
            ) : null}
            {employee.employment_status === "ACTIVE" ? (
              <>
                <Button
                  type="button"
                  className="button-secondary"
                  onClick={() => transition("leave")}
                >
                  Place on leave
                </Button>
                <Button
                  type="button"
                  className="button-secondary"
                  onClick={() => transition("suspend")}
                >
                  Suspend
                </Button>
                <Button
                  type="button"
                  className="button-danger"
                  onClick={() => transition("terminate", true)}
                >
                  Terminate
                </Button>
              </>
            ) : null}
            {employee.employment_status === "ON_LEAVE" ? (
              <Button
                type="button"
                onClick={() => transition("return-from-leave")}
              >
                Return from leave
              </Button>
            ) : null}
            {employee.employment_status === "SUSPENDED" ? (
              <Button type="button" onClick={() => transition("reinstate")}>
                Reinstate
              </Button>
            ) : null}
          </div>
        </section>
      ) : null}
      {auth.can("workforce.manage_employee_assignment") ? (
        <section className="detail-card">
          <h2>Organization assignment</h2>
          <p>
            Current: {employee.branch_name || "No branch"} |{" "}
            {employee.department_name || "No department"} |{" "}
            {employee.designation_name || "No designation"}
          </p>
          <details>
            <summary>Change assignment</summary>
            <form className="compact-form" onSubmit={changeAssignment}>
              {(["branches", "departments", "designations"] as const).map(
                (kind) => {
                  const field = kind.slice(0, -2);
                  return (
                    <label key={kind}>
                      {humanize(field)}
                      <select
                        name={field}
                        defaultValue={String(
                          employee[field as keyof Employee] ?? "",
                        )}
                      >
                        <option value="">Unassigned</option>
                        {references[kind]?.map((value) => (
                          <option key={value.id} value={value.id}>
                            {value.name}
                          </option>
                        ))}
                      </select>
                    </label>
                  );
                },
              )}
              <label>
                Reason
                <input name="reason" />
              </label>
              <Button>Save assignment</Button>
            </form>
          </details>
        </section>
      ) : null}
      <section className="detail-card">
        <h2>Addresses</h2>
        {addresses.length ? (
          <div className="card-list">
            {addresses.map((a) => (
              <article key={a.id}>
                <strong>
                  {humanize(a.address_type)}
                  {a.is_primary ? " - Primary" : ""}
                </strong>
                <p>
                  {[
                    a.address_line_1,
                    a.address_line_2,
                    a.city,
                    a.province_or_state,
                    a.country_code,
                  ]
                    .filter(Boolean)
                    .join(", ")}
                </p>
                {auth.can("workforce.change_employeeaddress") ? (
                  <details>
                    <summary>Edit address</summary>
                    <form
                      className="compact-form"
                      onSubmit={(event) => editAddress(event, a.id)}
                    >
                      <input
                        name="address_type"
                        type="hidden"
                        value={a.address_type}
                      />
                      <label>
                        Address
                        <input
                          name="address_line_1"
                          defaultValue={a.address_line_1}
                          required
                        />
                      </label>
                      <label>
                        City
                        <input name="city" defaultValue={a.city} required />
                      </label>
                      <label>
                        Country
                        <input
                          name="country_code"
                          defaultValue={a.country_code}
                          maxLength={2}
                          required
                        />
                      </label>
                      <Button>Update address</Button>
                    </form>
                  </details>
                ) : null}
              </article>
            ))}
          </div>
        ) : (
          <EmptyState message="No addresses recorded." />
        )}
        {auth.can("workforce.add_employeeaddress") ? (
          <details>
            <summary>Add address</summary>
            <form className="compact-form" onSubmit={addAddress}>
              <label>
                Type
                <select name="address_type">
                  <option value="CURRENT">Current</option>
                  <option value="PERMANENT">Permanent</option>
                  <option value="OTHER">Other</option>
                </select>
              </label>
              <label>
                Address
                <input name="address_line_1" required />
              </label>
              <label>
                City
                <input name="city" required />
              </label>
              <label>
                Country
                <input
                  name="country_code"
                  defaultValue="PK"
                  maxLength={2}
                  required
                />
              </label>
              <label className="checkbox-field">
                <input name="is_primary" type="checkbox" value="true" /> Primary
              </label>
              <Button>Add address</Button>
            </form>
          </details>
        ) : null}
      </section>
      <section className="detail-card">
        <h2>Emergency contacts</h2>
        {contacts.length ? (
          <div className="card-list">
            {contacts.map((c) => (
              <article key={c.id}>
                <strong>
                  {c.name}
                  {c.is_primary ? " - Primary" : ""}
                </strong>
                <p>
                  {c.relationship} · {c.mobile_number}
                </p>
                {auth.can("workforce.change_emergencycontact") ? (
                  <details>
                    <summary>Edit contact</summary>
                    <form
                      className="compact-form"
                      onSubmit={(event) => editContact(event, c.id)}
                    >
                      <label>
                        Name
                        <input name="name" defaultValue={c.name} required />
                      </label>
                      <label>
                        Relationship
                        <input
                          name="relationship"
                          defaultValue={c.relationship}
                          required
                        />
                      </label>
                      <label>
                        Mobile number
                        <input
                          name="mobile_number"
                          defaultValue={c.mobile_number}
                          required
                        />
                      </label>
                      <Button>Update contact</Button>
                    </form>
                  </details>
                ) : null}
              </article>
            ))}
          </div>
        ) : (
          <EmptyState message="No emergency contacts recorded." />
        )}
        {auth.can("workforce.add_emergencycontact") ? (
          <details>
            <summary>Add emergency contact</summary>
            <form className="compact-form" onSubmit={addContact}>
              <label>
                Name
                <input name="name" required />
              </label>
              <label>
                Relationship
                <input name="relationship" required />
              </label>
              <label>
                Mobile number
                <input name="mobile_number" required />
              </label>
              <label className="checkbox-field">
                <input name="is_primary" type="checkbox" value="true" /> Primary
              </label>
              <Button>Add contact</Button>
            </form>
          </details>
        ) : null}
      </section>
      <section className="detail-card">
        <h2>Employment history</h2>
        <h3>Status history</h3>
        {statuses.length ? (
          <ul className="timeline-list">
            {statuses.map((item) => (
              <li key={item.id}>
                <strong>
                  {humanize(item.previous_status)} to{" "}
                  {humanize(item.new_status)}
                </strong>
                <span>
                  {item.effective_date}
                  {item.reason ? ` - ${item.reason}` : ""}
                </span>
              </li>
            ))}
          </ul>
        ) : (
          <p>No status changes recorded.</p>
        )}
        <h3>Assignment history</h3>
        {assignments.length ? (
          <ul className="timeline-list">
            {assignments.map((item) => (
              <li key={item.id}>
                <strong>
                  {[
                    item.branch_name,
                    item.department_name,
                    item.designation_name,
                  ]
                    .filter(Boolean)
                    .join(" · ") || "Unassigned"}
                </strong>
                <span>
                  From {item.effective_from}
                  {item.effective_to ? ` to ${item.effective_to}` : ""}
                </span>
              </li>
            ))}
          </ul>
        ) : (
          <p>No assignment changes recorded.</p>
        )}
      </section>
      <section className="detail-card">
        <h2>Documents</h2>
        {documents.length ? (
          <ul className="document-list">
            {documents.map((document) => (
              <li key={document.id}>
                <strong>
                  {document.title ||
                    document.document_type_name ||
                    document.file_name ||
                    "Employee document"}
                </strong>
                {document.expiry_date ? (
                  <span>Expires {document.expiry_date}</span>
                ) : null}
              </li>
            ))}
          </ul>
        ) : (
          <EmptyState message="No employee documents available." />
        )}
        <p className="help-text">
          Document upload remains in the established Documents workflow.
        </p>
      </section>
    </div>
  );
}

export function EmployeeDetailPage({ id }: { id: string }) {
  const auth = useAuth();
  const companyId = auth.company_context.selected_company?.id;
  const [employee, setEmployee] = useState<Employee | null>(null);
  const [error, setError] = useState("");
  const requestId = useRef(0);
  const load = useCallback(() => {
    const request = ++requestId.current;
    getEmployee(id)
      .then((value) => {
        if (request === requestId.current) {
          setEmployee(value);
          setError("");
        }
      })
      .catch((reason) => {
        if (request === requestId.current) {
          setEmployee(null);
          setError(
            reason instanceof ApiError && reason.status === 404
              ? "Employee not found in the selected Company."
              : "Employee could not be loaded.",
          );
        }
      });
  }, [id]);
  useEffect(load, [companyId, load]);
  if (!auth.can("workforce.view_employee"))
    return (
      <ErrorState message="You do not have permission to view employees." />
    );
  if (error && !employee) return <ErrorState message={error} />;
  if (!employee || employee.company !== companyId)
    return <LoadingState label="Loading employee..." />;
  return (
    <>
      <PageHeader
        title={employee.full_name}
        description={`Employee ${employee.employee_number}`}
        actions={
          auth.can("workforce.change_employee") ? (
            <Link className="button" href={`/employees/${employee.id}/edit`}>
              Edit employee
            </Link>
          ) : undefined
        }
      />
      <section className="detail-card">
        <div className="detail-heading">
          <Status value={employee.employment_status} />
        </div>
        <dl className="detail-grid">
          <dt>Employee type</dt>
          <dd>
            {employeeTypeLabel(
              employee.employee_type,
              auth.hasModule("security_operations"),
            )}
          </dd>
          <dt>Employment type</dt>
          <dd>{humanize(employee.employment_type)}</dd>
          <dt>Joining date</dt>
          <dd>{employee.joining_date}</dd>
          <dt>Company</dt>
          <dd>{employee.company_name}</dd>
          <dt>Branch</dt>
          <dd>{employee.branch_name || "-"}</dd>
          <dt>Department</dt>
          <dd>{employee.department_name || "-"}</dd>
          <dt>Designation</dt>
          <dd>{employee.designation_name || "-"}</dd>
          <dt>Email</dt>
          <dd>{employee.personal_email || "-"}</dd>
          <dt>Mobile</dt>
          <dd>{employee.mobile_number}</dd>
          <dt>Identity</dt>
          <dd>{employee.masked_national_identity_number || "Not recorded"}</dd>
        </dl>
      </section>
      <RelatedPeopleData employee={employee} reloadEmployee={load} />
    </>
  );
}
