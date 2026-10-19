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
  activateClient,
  contractAction,
  getClient,
  getContract,
  listAmendments,
  listClientContacts,
  listClients,
  listCommercialTerms,
  listContracts,
  listContractServices,
  listIndustries,
  listServiceLevels,
  saveClient,
  saveClientContact,
  saveCommercialTerms,
  saveContract,
  saveContractService,
} from "./api";
import type {
  Amendment,
  Client,
  ClientContact,
  CommercialTerms,
  Contract,
  ContractService,
  Industry,
  ServiceLevel,
} from "./types";

const humanize = (value?: string | null) =>
  value
    ? value
        .replaceAll("_", " ")
        .toLowerCase()
        .replace(/^./, (c) => c.toUpperCase())
    : "-";
const selectedCompany = (auth: ReturnType<typeof useAuth>) =>
  auth.company_context.selected_company?.id;

function Status({ value }: { value: string }) {
  return (
    <span className={`status-badge status-${value.toLowerCase()}`}>
      {humanize(value)}
    </span>
  );
}

export function ClientListPage({
  searchParams,
}: {
  searchParams: Record<string, string>;
}) {
  const auth = useAuth();
  const companyId = selectedCompany(auth);
  const [data, setData] = useState<Awaited<
    ReturnType<typeof listClients>
  > | null>(null);
  const [loadedFor, setLoadedFor] = useState<string | null>(null);
  const [industries, setIndustries] = useState<Industry[]>([]);
  const [error, setError] = useState("");
  const [errorFor, setErrorFor] = useState<string | null>(null);
  useEffect(() => {
    if (!companyId || !auth.can("contracts.view_client")) return;
    let current = true;
    Promise.all([listClients(searchParams), listIndustries()])
      .then(([clients, refs]) => {
        if (current) {
          setData(clients);
          setLoadedFor(companyId);
          setError("");
          setIndustries(refs);
        }
      })
      .catch(() => {
        if (current) {
          setErrorFor(companyId);
          setError("Clients could not be loaded.");
        }
      });
    return () => {
      current = false;
    };
  }, [auth, companyId, searchParams]);
  if (!auth.can("contracts.view_client"))
    return <ErrorState message="You do not have permission to view clients." />;
  const visibleData = loadedFor === companyId ? data : null;
  const visibleError = errorFor === companyId ? error : "";
  return (
    <>
      <PageHeader
        title="Clients"
        description="Manage Company customer and business relationship records."
        actions={
          auth.can("contracts.add_client") ? (
            <Link className="button" href="/clients/new">
              Add client
            </Link>
          ) : undefined
        }
      />
      <form className="invoice-filters" action="/clients">
        <label>
          Search
          <input
            name="search"
            defaultValue={searchParams.search}
            placeholder="Name, code, registration, tax, or email"
          />
        </label>
        <label>
          Status
          <select name="status" defaultValue={searchParams.status}>
            <option value="">All statuses</option>
            {[
              "PROSPECT",
              "ACTIVE",
              "SUSPENDED",
              "INACTIVE",
              "BLACKLISTED",
              "ARCHIVED",
            ].map((v) => (
              <option key={v} value={v}>
                {humanize(v)}
              </option>
            ))}
          </select>
        </label>
        <label>
          Industry
          <select name="industry" defaultValue={searchParams.industry}>
            <option value="">All industries</option>
            {industries.map((value) => (
              <option key={value.id} value={value.id}>
                {value.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          Order
          <select
            name="ordering"
            defaultValue={searchParams.ordering || "legal_name"}
          >
            <option value="legal_name">Name</option>
            <option value="client_code">Client code</option>
            <option value="-created_at">Newest</option>
          </select>
        </label>
        <div className="filter-actions">
          <Button type="submit">Apply</Button>
          <Link className="button button-secondary" href="/clients">
            Clear
          </Link>
        </div>
      </form>
      {visibleError ? (
        <ErrorState message={visibleError} />
      ) : !visibleData ? (
        <LoadingState label="Loading clients..." />
      ) : !visibleData.results.length ? (
        <EmptyState
          message="No clients yet."
          action={
            auth.can("contracts.add_client") ? (
              <Link className="button" href="/clients/new">
                Add client
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
                  <th>Client</th>
                  <th>Industry</th>
                  <th>Contact</th>
                  <th>Location</th>
                  <th>Status</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {visibleData.results.map((client) => (
                  <tr key={client.id}>
                    <td>
                      <Link href={`/clients/${client.id}`}>
                        {client.legal_name}
                      </Link>
                      <small className="table-secondary">
                        {client.client_code}
                        {client.trade_name ? ` · ${client.trade_name}` : ""}
                      </small>
                    </td>
                    <td>{client.industry_name}</td>
                    <td>{client.main_email || client.main_phone || "-"}</td>
                    <td>
                      {[client.city, client.country_code]
                        .filter(Boolean)
                        .join(", ") || "-"}
                    </td>
                    <td>
                      <Status value={client.status} />
                    </td>
                    <td>
                      {auth.can("contracts.change_client") ? (
                        <Link href={`/clients/${client.id}/edit`}>Edit</Link>
                      ) : (
                        "-"
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <nav className="pagination" aria-label="Client pages">
            {visibleData.previous ? (
              <Link
                href={{
                  pathname: "/clients",
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
            <span>{visibleData.count} clients</span>
            {visibleData.next ? (
              <Link
                href={{
                  pathname: "/clients",
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

const blankClient = {
  client_code: "",
  legal_name: "",
  trade_name: "",
  industry: "",
  registration_number: "",
  tax_number: "",
  website: "",
  main_email: "",
  main_phone: "",
  billing_address: "",
  head_office_address: "",
  city: "",
  province_or_state: "",
  country_code: "PK",
  notes: "",
};
function ClientForm({ client }: { client?: Client }) {
  const auth = useAuth();
  const router = useRouter();
  const [values, setValues] = useState({
    ...blankClient,
    ...(client
      ? Object.fromEntries(
          Object.keys(blankClient).map((key) => [
            key,
            String(client[key as keyof Client] ?? ""),
          ]),
        )
      : {}),
  });
  const [industries, setIndustries] = useState<Industry[]>([]);
  const [errors, setErrors] = useState<Record<string, string[]>>({});
  const [message, setMessage] = useState("");
  const [pending, setPending] = useState(false);
  useEffect(() => {
    listIndustries()
      .then(setIndustries)
      .catch(() => setMessage("Industries could not be loaded."));
  }, []);
  const permission = client
    ? "contracts.change_client"
    : "contracts.add_client";
  if (!auth.can(permission))
    return (
      <ErrorState message="You do not have permission to manage this client." />
    );
  const set = (field: string, value: string) =>
    setValues((current) => ({ ...current, [field]: value }));
  async function submit(event: FormEvent) {
    event.preventDefault();
    setPending(true);
    setErrors({});
    setMessage("");
    try {
      const saved = await saveClient(client?.id ?? null, values);
      router.push(`/clients/${saved.id}`);
    } catch (reason) {
      if (reason instanceof ApiError) {
        setErrors(reason.fieldErrors);
        setMessage(reason.message);
      } else setMessage("The client could not be saved.");
    } finally {
      setPending(false);
    }
  }
  return (
    <form className="invoice-form" onSubmit={submit}>
      <fieldset>
        <legend>Business identity</legend>
        <FormField
          id="client_code"
          label="Client code"
          required
          value={values.client_code}
          onChange={(e) => set("client_code", e.target.value)}
          error={errors.client_code?.[0]}
        />
        <FormField
          id="legal_name"
          label="Legal name"
          required
          value={values.legal_name}
          onChange={(e) => set("legal_name", e.target.value)}
          error={errors.legal_name?.[0]}
        />
        <FormField
          id="trade_name"
          label="Trade name"
          value={values.trade_name}
          onChange={(e) => set("trade_name", e.target.value)}
        />
        <label className="form-field">
          <span>Industry</span>
          <select
            required
            value={values.industry}
            onChange={(e) => set("industry", e.target.value)}
          >
            <option value="">Select an industry</option>
            {industries
              .filter((i) => i.is_active)
              .map((i) => (
                <option key={i.id} value={i.id}>
                  {i.name}
                </option>
              ))}
          </select>
          {errors.industry?.[0] ? (
            <span className="field-error">{errors.industry[0]}</span>
          ) : null}
        </label>
        <FormField
          id="registration_number"
          label="Registration number"
          value={values.registration_number}
          onChange={(e) => set("registration_number", e.target.value)}
        />
        <FormField
          id="tax_number"
          label="Tax number"
          value={values.tax_number}
          onChange={(e) => set("tax_number", e.target.value)}
        />
      </fieldset>
      <fieldset>
        <legend>Contact</legend>
        <FormField
          id="main_email"
          label="Main email"
          type="email"
          value={values.main_email}
          onChange={(e) => set("main_email", e.target.value)}
        />
        <FormField
          id="main_phone"
          label="Main phone"
          value={values.main_phone}
          onChange={(e) => set("main_phone", e.target.value)}
        />
        <FormField
          id="website"
          label="Website"
          type="url"
          value={values.website}
          onChange={(e) => set("website", e.target.value)}
        />
      </fieldset>
      <fieldset>
        <legend>Address</legend>
        <FormField
          id="head_office_address"
          label="Head office address"
          value={values.head_office_address}
          onChange={(e) => set("head_office_address", e.target.value)}
        />
        <FormField
          id="billing_address"
          label="Billing address"
          value={values.billing_address}
          onChange={(e) => set("billing_address", e.target.value)}
        />
        <FormField
          id="city"
          label="City"
          value={values.city}
          onChange={(e) => set("city", e.target.value)}
        />
        <FormField
          id="province_or_state"
          label="Province or state"
          value={values.province_or_state}
          onChange={(e) => set("province_or_state", e.target.value)}
        />
        <FormField
          id="country_code"
          label="Country code"
          maxLength={2}
          required
          value={values.country_code}
          onChange={(e) => set("country_code", e.target.value.toUpperCase())}
        />
      </fieldset>
      <FormError message={message} />
      <div className="filter-actions">
        <Button disabled={pending}>
          {pending ? "Saving..." : "Save client"}
        </Button>
        <Link
          className="button button-secondary"
          href={client ? `/clients/${client.id}` : "/clients"}
        >
          Cancel
        </Link>
      </div>
    </form>
  );
}
export function ClientCreatePage() {
  return (
    <>
      <PageHeader
        title="Add client"
        description="Create a Company client record."
      />
      <ClientForm />
    </>
  );
}
export function ClientEditPage({ id }: { id: string }) {
  const auth = useAuth();
  const companyId = selectedCompany(auth);
  const [client, setClient] = useState<Client | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    let current = true;
    getClient(id)
      .then((value) => current && setClient(value))
      .catch(
        (reason) =>
          current &&
          setError(
            reason instanceof ApiError && reason.status === 404
              ? "Client not found."
              : "Client could not be loaded.",
          ),
      );
    return () => {
      current = false;
    };
  }, [companyId, id]);
  return error ? (
    <ErrorState message={error} />
  ) : !client || client.company !== companyId ? (
    <LoadingState label="Loading client..." />
  ) : (
    <>
      <PageHeader
        title={`Edit ${client.legal_name}`}
        description={client.client_code}
      />
      <ClientForm client={client} />
    </>
  );
}

function ClientRelationships({ client }: { client: Client }) {
  const auth = useAuth();
  const [contacts, setContacts] = useState<ClientContact[]>([]);
  const [contracts, setContracts] = useState<Contract[]>([]);
  const [message, setMessage] = useState("");
  const load = useCallback(
    () =>
      Promise.all([
        listClientContacts(client.id),
        listContracts({ client: client.id, ordering: "-start_date" }),
      ]).then(([contactPage, contractPage]) => {
        setContacts(contactPage.results);
        setContracts(contractPage.results);
      }),
    [client.id],
  );
  useEffect(() => {
    load().catch(() =>
      setMessage("Related client information could not be loaded."),
    );
  }, [client.id, load]);
  async function addContact(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = Object.fromEntries(new FormData(form));
    try {
      await saveClientContact(null, {
        ...data,
        client: client.id,
        is_active: true,
        is_primary: data.is_primary === "true",
      });
      form.reset();
      await load();
    } catch (reason) {
      setMessage(
        reason instanceof ApiError
          ? reason.message
          : "Contact could not be saved.",
      );
    }
  }
  async function editContact(
    event: FormEvent<HTMLFormElement>,
    contact: ClientContact,
  ) {
    event.preventDefault();
    try {
      await saveClientContact(contact.id, {
        ...Object.fromEntries(new FormData(event.currentTarget)),
        client: client.id,
      });
      await load();
    } catch (reason) {
      setMessage(
        reason instanceof ApiError
          ? reason.message
          : "Contact could not be updated.",
      );
    }
  }
  return (
    <div className="workspace-sections">
      <FormError message={message} />
      <section className="detail-card">
        <h2>Contacts</h2>
        {contacts.length ? (
          <div className="card-list">
            {contacts.map((contact) => (
              <article key={contact.id}>
                <strong>
                  {contact.name}
                  {contact.is_primary ? " - Primary" : ""}
                </strong>
                <p>
                  {[
                    humanize(contact.contact_type),
                    contact.designation,
                    contact.email || contact.mobile_number,
                  ]
                    .filter(Boolean)
                    .join(" · ")}
                </p>
                {auth.can("contracts.change_clientcontact") ? (
                  <details>
                    <summary>Edit contact</summary>
                    <form
                      className="compact-form"
                      onSubmit={(event) => editContact(event, contact)}
                    >
                      <input
                        name="contact_type"
                        type="hidden"
                        value={contact.contact_type}
                      />
                      <label>
                        Name
                        <input
                          name="name"
                          defaultValue={contact.name}
                          required
                        />
                      </label>
                      <label>
                        Email
                        <input
                          name="email"
                          type="email"
                          defaultValue={contact.email}
                        />
                      </label>
                      <label>
                        Mobile
                        <input
                          name="mobile_number"
                          defaultValue={contact.mobile_number}
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
          <EmptyState message="No client contacts yet." />
        )}
        {auth.can("contracts.add_clientcontact") ? (
          <details>
            <summary>Add contact</summary>
            <form className="compact-form" onSubmit={addContact}>
              <label>
                Name
                <input name="name" required />
              </label>
              <label>
                Type
                <select name="contact_type">
                  <option value="PRIMARY">Primary</option>
                  <option value="OPERATIONS">Operations</option>
                  <option value="FINANCE">Finance</option>
                  <option value="HR">HR</option>
                  <option value="OTHER">Other</option>
                </select>
              </label>
              <label>
                Email
                <input name="email" type="email" />
              </label>
              <label>
                Mobile
                <input name="mobile_number" />
              </label>
              <label className="checkbox-field">
                <input name="is_primary" type="checkbox" value="true" /> Primary
                contact
              </label>
              <Button>Add contact</Button>
            </form>
          </details>
        ) : null}
      </section>
      <section className="detail-card">
        <div className="section-heading">
          <h2>Contracts</h2>
          {auth.can("contracts.add_servicecontract") ? (
            <Link href={`/contracts/new?client=${client.id}`}>
              Create contract
            </Link>
          ) : null}
        </div>
        {contracts.length ? (
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Contract</th>
                  <th>Dates</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {contracts.map((contract) => (
                  <tr key={contract.id}>
                    <td>
                      <Link href={`/contracts/${contract.id}`}>
                        {contract.title}
                      </Link>
                      <small className="table-secondary">
                        {contract.contract_number}
                      </small>
                    </td>
                    <td>
                      {contract.start_date} to{" "}
                      {contract.end_date || "Open ended"}
                    </td>
                    <td>
                      <Status value={contract.status} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <EmptyState message="No contracts yet." />
        )}
      </section>
    </div>
  );
}

export function ClientDetailPage({ id }: { id: string }) {
  const auth = useAuth();
  const companyId = selectedCompany(auth);
  const [client, setClient] = useState<Client | null>(null);
  const [error, setError] = useState("");
  const requestId = useRef(0);
  const load = useCallback(() => {
    const request = ++requestId.current;
    getClient(id)
      .then((value) => {
        if (request === requestId.current) {
          setClient(value);
          setError("");
        }
      })
      .catch((reason) => {
        if (request === requestId.current) {
          setClient(null);
          setError(
            reason instanceof ApiError && reason.status === 404
              ? "Client not found in the selected Company."
              : "Client could not be loaded.",
          );
        }
      });
  }, [id]);
  useEffect(load, [companyId, load]);
  if (!auth.can("contracts.view_client"))
    return <ErrorState message="You do not have permission to view clients." />;
  if (error) return <ErrorState message={error} />;
  if (!client || client.company !== companyId)
    return <LoadingState label="Loading client..." />;
  return (
    <>
      <PageHeader
        title={client.legal_name}
        description={`Client ${client.client_code}`}
        actions={
          <div className="quick-actions">
            {auth.can("contracts.change_client") ? (
              <Link className="button" href={`/clients/${client.id}/edit`}>
                Edit client
              </Link>
            ) : null}
            {auth.can("contracts.change_client") &&
            client.status === "PROSPECT" ? (
              <Button
                type="button"
                onClick={() =>
                  activateClient(client.id)
                    .then(load)
                    .catch(() => setError("Client could not be activated."))
                }
              >
                Activate
              </Button>
            ) : null}
          </div>
        }
      />
      <section className="detail-card">
        <div className="detail-heading">
          <Status value={client.status} />
        </div>
        <dl className="detail-grid">
          <dt>Trade name</dt>
          <dd>{client.trade_name || "-"}</dd>
          <dt>Industry</dt>
          <dd>{client.industry_name}</dd>
          <dt>Registration</dt>
          <dd>{client.registration_number || "-"}</dd>
          <dt>Tax number</dt>
          <dd>{client.tax_number || "-"}</dd>
          <dt>Email</dt>
          <dd>{client.main_email || "-"}</dd>
          <dt>Phone</dt>
          <dd>{client.main_phone || "-"}</dd>
          <dt>Website</dt>
          <dd>
            {client.website ? (
              <a href={client.website}>{client.website}</a>
            ) : (
              "-"
            )}
          </dd>
          <dt>Location</dt>
          <dd>
            {[client.city, client.province_or_state, client.country_code]
              .filter(Boolean)
              .join(", ") || "-"}
          </dd>
          <dt>Account manager</dt>
          <dd>{client.account_manager_name || "Unassigned"}</dd>
        </dl>
      </section>
      <ClientRelationships client={client} />
    </>
  );
}

export function ContractListPage({
  searchParams,
}: {
  searchParams: Record<string, string>;
}) {
  const auth = useAuth();
  const companyId = selectedCompany(auth);
  const [data, setData] = useState<Awaited<
    ReturnType<typeof listContracts>
  > | null>(null);
  const [loadedFor, setLoadedFor] = useState<string | null>(null);
  const [clients, setClients] = useState<Client[]>([]);
  const [error, setError] = useState("");
  const [errorFor, setErrorFor] = useState<string | null>(null);
  useEffect(() => {
    if (!companyId || !auth.can("contracts.view_servicecontract")) return;
    let current = true;
    Promise.all([
      listContracts(searchParams),
      listClients({ ordering: "legal_name" }),
    ])
      .then(([contracts, clientPage]) => {
        if (current) {
          setData(contracts);
          setLoadedFor(companyId);
          setError("");
          setClients(clientPage.results);
        }
      })
      .catch(() => {
        if (current) {
          setErrorFor(companyId);
          setError("Contracts could not be loaded.");
        }
      });
    return () => {
      current = false;
    };
  }, [auth, companyId, searchParams]);
  if (!auth.can("contracts.view_servicecontract"))
    return (
      <ErrorState message="You do not have permission to view contracts." />
    );
  const visibleData = loadedFor === companyId ? data : null;
  const visibleError = errorFor === companyId ? error : "";
  return (
    <>
      <PageHeader
        title="Contracts"
        description="Manage generic Company service agreements and commercial context."
        actions={
          auth.can("contracts.add_servicecontract") ? (
            <Link className="button" href="/contracts/new">
              Create contract
            </Link>
          ) : undefined
        }
      />
      <form className="invoice-filters" action="/contracts">
        <label>
          Search
          <input
            name="search"
            defaultValue={searchParams.search}
            placeholder="Number, title, client, or reference"
          />
        </label>
        <label>
          Client
          <select name="client" defaultValue={searchParams.client}>
            <option value="">All clients</option>
            {clients.map((value) => (
              <option key={value.id} value={value.id}>
                {value.legal_name}
              </option>
            ))}
          </select>
        </label>
        <label>
          Status
          <select name="status" defaultValue={searchParams.status}>
            <option value="">All statuses</option>
            {[
              "DRAFT",
              "PENDING_APPROVAL",
              "APPROVED",
              "ACTIVE",
              "SUSPENDED",
              "EXPIRED",
              "TERMINATED",
              "COMPLETED",
              "CANCELLED",
            ].map((v) => (
              <option key={v} value={v}>
                {humanize(v)}
              </option>
            ))}
          </select>
        </label>
        <label>
          Order
          <select
            name="ordering"
            defaultValue={searchParams.ordering || "-start_date"}
          >
            <option value="-start_date">Newest start date</option>
            <option value="start_date">Oldest start date</option>
            <option value="contract_number">Contract number</option>
            <option value="end_date">Expiry date</option>
          </select>
        </label>
        <div className="filter-actions">
          <Button type="submit">Apply</Button>
          <Link className="button button-secondary" href="/contracts">
            Clear
          </Link>
        </div>
      </form>
      {visibleError ? (
        <ErrorState message={visibleError} />
      ) : !visibleData ? (
        <LoadingState label="Loading contracts..." />
      ) : !visibleData.results.length ? (
        <EmptyState
          message="No contracts yet."
          action={
            auth.can("contracts.add_servicecontract") ? (
              <Link className="button" href="/contracts/new">
                Create contract
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
                  <th>Contract</th>
                  <th>Client</th>
                  <th>Type</th>
                  <th>Effective dates</th>
                  <th>Status</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {visibleData.results.map((contract) => (
                  <tr key={contract.id}>
                    <td>
                      <Link href={`/contracts/${contract.id}`}>
                        {contract.title}
                      </Link>
                      <small className="table-secondary">
                        {contract.contract_number}
                      </small>
                    </td>
                    <td>{contract.client_name}</td>
                    <td>{humanize(contract.contract_type)}</td>
                    <td>
                      {contract.start_date} to{" "}
                      {contract.end_date || "Open ended"}
                    </td>
                    <td>
                      <Status value={contract.status} />
                    </td>
                    <td>
                      {auth.can("contracts.change_servicecontract") &&
                      contract.status === "DRAFT" ? (
                        <Link href={`/contracts/${contract.id}/edit`}>
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
          <nav className="pagination" aria-label="Contract pages">
            {visibleData.previous ? (
              <Link
                href={{
                  pathname: "/contracts",
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
            <span>{visibleData.count} contracts</span>
            {visibleData.next ? (
              <Link
                href={{
                  pathname: "/contracts",
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

const blankContract = {
  client: "",
  contract_number: "",
  contract_type: "FIXED_TERM",
  title: "",
  description: "",
  signed_date: "",
  start_date: "",
  end_date: "",
  notice_period_days: "",
  auto_renew: false,
  currency: "PKR",
  client_reference: "",
  purchase_order_reference: "",
  internal_reference: "",
};
function ContractForm({
  contract,
  initialClient,
}: {
  contract?: Contract;
  initialClient?: string;
}) {
  const auth = useAuth();
  const router = useRouter();
  const [clients, setClients] = useState<Client[]>([]);
  const [values, setValues] = useState({
    ...blankContract,
    client: initialClient || "",
    ...(contract
      ? Object.fromEntries(
          Object.keys(blankContract).map((key) => [
            key,
            contract[key as keyof Contract] ?? "",
          ]),
        )
      : {}),
  });
  const [errors, setErrors] = useState<Record<string, string[]>>({});
  const [message, setMessage] = useState("");
  const [pending, setPending] = useState(false);
  useEffect(() => {
    listClients({ status: "ACTIVE", ordering: "legal_name" })
      .then((page) => setClients(page.results))
      .catch(() => setMessage("Clients could not be loaded."));
  }, []);
  const permission = contract
    ? "contracts.change_servicecontract"
    : "contracts.add_servicecontract";
  if (!auth.can(permission))
    return (
      <ErrorState message="You do not have permission to manage this contract." />
    );
  const set = (field: string, value: string | boolean) =>
    setValues((current) => ({ ...current, [field]: value }));
  async function submit(event: FormEvent) {
    event.preventDefault();
    setPending(true);
    setErrors({});
    setMessage("");
    const body = Object.fromEntries(
      Object.entries(values).filter(([, value]) => value !== ""),
    );
    try {
      const saved = await saveContract(contract?.id ?? null, body);
      router.push(`/contracts/${saved.id}`);
    } catch (reason) {
      if (reason instanceof ApiError) {
        setErrors(reason.fieldErrors);
        setMessage(reason.message);
      } else setMessage("The contract could not be saved.");
    } finally {
      setPending(false);
    }
  }
  return (
    <form className="invoice-form" onSubmit={submit}>
      <fieldset>
        <legend>Agreement</legend>
        <label className="form-field">
          <span>Client</span>
          <select
            required
            value={String(values.client)}
            onChange={(e) => set("client", e.target.value)}
          >
            <option value="">Select a client</option>
            {clients.map((client) => (
              <option key={client.id} value={client.id}>
                {client.legal_name}
              </option>
            ))}
          </select>
          {errors.client?.[0] ? (
            <span className="field-error">{errors.client[0]}</span>
          ) : null}
        </label>
        <FormField
          id="contract_number"
          label="Contract number"
          required
          value={String(values.contract_number)}
          onChange={(e) => set("contract_number", e.target.value)}
          error={errors.contract_number?.[0]}
        />
        <FormField
          id="title"
          label="Title"
          required
          value={String(values.title)}
          onChange={(e) => set("title", e.target.value)}
          error={errors.title?.[0]}
        />
        <label className="form-field">
          <span>Contract type</span>
          <select
            value={String(values.contract_type)}
            onChange={(e) => set("contract_type", e.target.value)}
          >
            {["FIXED_TERM", "OPEN_ENDED", "PROJECT", "FRAMEWORK", "OTHER"].map(
              (v) => (
                <option key={v} value={v}>
                  {humanize(v)}
                </option>
              ),
            )}
          </select>
        </label>
        <label className="form-field">
          <span>Description</span>
          <textarea
            value={String(values.description)}
            onChange={(e) => set("description", e.target.value)}
          />
        </label>
      </fieldset>
      <fieldset>
        <legend>Dates and references</legend>
        <FormField
          id="start_date"
          label="Start date"
          type="date"
          required
          value={String(values.start_date)}
          onChange={(e) => set("start_date", e.target.value)}
          error={errors.start_date?.[0]}
        />
        <FormField
          id="end_date"
          label="End date"
          type="date"
          value={String(values.end_date)}
          onChange={(e) => set("end_date", e.target.value)}
        />
        <FormField
          id="signed_date"
          label="Signed date"
          type="date"
          value={String(values.signed_date)}
          onChange={(e) => set("signed_date", e.target.value)}
        />
        <FormField
          id="client_reference"
          label="Client reference"
          value={String(values.client_reference)}
          onChange={(e) => set("client_reference", e.target.value)}
        />
        <FormField
          id="purchase_order_reference"
          label="Purchase order reference"
          value={String(values.purchase_order_reference)}
          onChange={(e) => set("purchase_order_reference", e.target.value)}
        />
        <FormField
          id="internal_reference"
          label="Internal reference"
          value={String(values.internal_reference)}
          onChange={(e) => set("internal_reference", e.target.value)}
        />
      </fieldset>
      <fieldset>
        <legend>Commercial defaults</legend>
        <FormField
          id="currency"
          label="Currency"
          maxLength={3}
          required
          value={String(values.currency)}
          onChange={(e) => set("currency", e.target.value.toUpperCase())}
        />
        <FormField
          id="notice_period_days"
          label="Notice period (days)"
          type="number"
          min="0"
          value={String(values.notice_period_days)}
          onChange={(e) => set("notice_period_days", e.target.value)}
        />
        <label className="checkbox-field">
          <input
            type="checkbox"
            checked={Boolean(values.auto_renew)}
            onChange={(e) => set("auto_renew", e.target.checked)}
          />{" "}
          Auto renew
        </label>
      </fieldset>
      <FormError message={message} />
      <div className="filter-actions">
        <Button disabled={pending}>
          {pending ? "Saving..." : "Save contract"}
        </Button>
        <Link
          className="button button-secondary"
          href={contract ? `/contracts/${contract.id}` : "/contracts"}
        >
          Cancel
        </Link>
      </div>
    </form>
  );
}
export function ContractCreatePage({
  initialClient,
}: {
  initialClient?: string;
}) {
  return (
    <>
      <PageHeader
        title="Create contract"
        description="Create a generic service agreement without operational dependencies."
      />
      <ContractForm initialClient={initialClient} />
    </>
  );
}
export function ContractEditPage({ id }: { id: string }) {
  const auth = useAuth();
  const companyId = selectedCompany(auth);
  const [contract, setContract] = useState<Contract | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    let current = true;
    getContract(id)
      .then((value) => current && setContract(value))
      .catch(
        (reason) =>
          current &&
          setError(
            reason instanceof ApiError && reason.status === 404
              ? "Contract not found."
              : "Contract could not be loaded.",
          ),
      );
    return () => {
      current = false;
    };
  }, [companyId, id]);
  return error ? (
    <ErrorState message={error} />
  ) : !contract || contract.company !== companyId ? (
    <LoadingState label="Loading contract..." />
  ) : (
    <>
      <PageHeader
        title={`Edit ${contract.contract_number}`}
        description={contract.title}
      />
      <ContractForm contract={contract} />
    </>
  );
}

function ContractPanels({ contract }: { contract: Contract }) {
  const auth = useAuth();
  const [services, setServices] = useState<ContractService[]>([]);
  const [terms, setTerms] = useState<CommercialTerms | null>(null);
  const [amendments, setAmendments] = useState<Amendment[]>([]);
  const [levels, setLevels] = useState<ServiceLevel[]>([]);
  const [message, setMessage] = useState("");
  const load = useCallback(
    () =>
      Promise.all([
        listContractServices(contract.id),
        listCommercialTerms(contract.id),
        listAmendments(contract.id),
        listServiceLevels(contract.id),
      ]).then(([s, t, a, l]) => {
        setServices(s.results);
        setTerms(t.results[0] ?? null);
        setAmendments(a.results);
        setLevels(l.results.filter((value) => value.site === null));
      }),
    [contract.id],
  );
  useEffect(() => {
    load().catch(() => setMessage("Contract details could not be loaded."));
  }, [contract.id, load]);
  async function addService(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    try {
      await saveContractService(null, {
        ...Object.fromEntries(new FormData(form)),
        contract: contract.id,
        is_active: true,
      });
      form.reset();
      await load();
    } catch (reason) {
      setMessage(
        reason instanceof ApiError
          ? reason.message
          : "Service could not be saved.",
      );
    }
  }
  async function editService(
    event: FormEvent<HTMLFormElement>,
    service: ContractService,
  ) {
    event.preventDefault();
    try {
      await saveContractService(service.id, {
        ...Object.fromEntries(new FormData(event.currentTarget)),
        contract: contract.id,
      });
      await load();
    } catch (reason) {
      setMessage(
        reason instanceof ApiError
          ? reason.message
          : "Service could not be updated.",
      );
    }
  }
  async function saveTerms(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    try {
      await saveCommercialTerms(terms?.id ?? null, {
        ...Object.fromEntries(new FormData(event.currentTarget)),
        contract: contract.id,
      });
      await load();
    } catch (reason) {
      setMessage(
        reason instanceof ApiError
          ? reason.message
          : "Commercial terms could not be saved.",
      );
    }
  }
  return (
    <div className="workspace-sections">
      <FormError message={message} />
      <section className="detail-card">
        <h2>Commercial terms</h2>
        {terms ? (
          <dl className="detail-grid">
            <dt>Billing frequency</dt>
            <dd>{humanize(terms.billing_frequency)}</dd>
            <dt>Agreed value</dt>
            <dd>
              {terms.agreed_contract_value
                ? `${contract.currency} ${terms.agreed_contract_value}`
                : "-"}
            </dd>
            <dt>Monthly value</dt>
            <dd>
              {terms.monthly_service_value
                ? `${contract.currency} ${terms.monthly_service_value}`
                : "-"}
            </dd>
            <dt>Payment terms</dt>
            <dd>
              {terms.payment_terms_days == null
                ? "-"
                : `${terms.payment_terms_days} days`}
            </dd>
          </dl>
        ) : (
          <EmptyState message="No commercial terms recorded." />
        )}
        {auth.can(
          terms
            ? "contracts.change_contractcommercialterms"
            : "contracts.add_contractcommercialterms",
        ) ? (
          <details>
            <summary>{terms ? "Edit terms" : "Add terms"}</summary>
            <form className="compact-form" onSubmit={saveTerms}>
              <label>
                Billing frequency
                <input
                  name="billing_frequency"
                  defaultValue={terms?.billing_frequency || "MONTHLY"}
                  required
                />
              </label>
              <label>
                Agreed contract value
                <input
                  name="agreed_contract_value"
                  type="number"
                  step="0.01"
                  defaultValue={terms?.agreed_contract_value || ""}
                />
              </label>
              <label>
                Monthly service value
                <input
                  name="monthly_service_value"
                  type="number"
                  step="0.01"
                  defaultValue={terms?.monthly_service_value || ""}
                />
              </label>
              <label>
                Payment terms (days)
                <input
                  name="payment_terms_days"
                  type="number"
                  min="0"
                  defaultValue={terms?.payment_terms_days ?? ""}
                />
              </label>
              <Button>Save terms</Button>
            </form>
          </details>
        ) : null}
      </section>
      <section className="detail-card">
        <h2>Services</h2>
        {services.length ? (
          <div className="card-list">
            {services.map((service) => (
              <article key={service.id}>
                <strong>{service.name}</strong>
                <p>
                  {humanize(service.service_type)}
                  {service.start_date ? ` · From ${service.start_date}` : ""}
                </p>
                {auth.can("contracts.change_contractservice") ? (
                  <details>
                    <summary>Edit service</summary>
                    <form
                      className="compact-form"
                      onSubmit={(event) => editService(event, service)}
                    >
                      <input
                        name="service_type"
                        type="hidden"
                        value={service.service_type}
                      />
                      <label>
                        Name
                        <input
                          name="name"
                          defaultValue={service.name}
                          required
                        />
                      </label>
                      <label>
                        Description
                        <textarea
                          name="description"
                          defaultValue={service.description}
                        />
                      </label>
                      <Button>Update service</Button>
                    </form>
                  </details>
                ) : null}
              </article>
            ))}
          </div>
        ) : (
          <EmptyState message="No generic services recorded." />
        )}
        {auth.can("contracts.add_contractservice") ? (
          <details>
            <summary>Add service</summary>
            <form className="compact-form" onSubmit={addService}>
              <label>
                Service type
                <select name="service_type">
                  <option value="CONSULTANCY">Consultancy</option>
                  <option value="OTHER">Other</option>
                </select>
              </label>
              <label>
                Name
                <input name="name" required />
              </label>
              <label>
                Description
                <textarea name="description" />
              </label>
              <label>
                Start date
                <input name="start_date" type="date" />
              </label>
              <label>
                End date
                <input name="end_date" type="date" />
              </label>
              <Button>Add service</Button>
            </form>
          </details>
        ) : null}
      </section>
      <section className="detail-card">
        <h2>Amendments</h2>
        {amendments.length ? (
          <ul className="timeline-list">
            {amendments.map((item) => (
              <li key={item.id}>
                <strong>
                  #{item.amendment_number} · {item.title}
                </strong>
                <span>
                  {item.effective_date} · {humanize(item.change_type)}
                </span>
              </li>
            ))}
          </ul>
        ) : (
          <EmptyState message="No approved amendments recorded." />
        )}
        <p className="help-text">Approved amendments are read-only history.</p>
      </section>
      <section className="detail-card">
        <h2>Service levels</h2>
        {levels.length ? (
          <div className="card-list">
            {levels.map((level) => (
              <article key={level.id}>
                <strong>{level.name}</strong>
                <p>
                  {level.target_value || "-"} {level.target_unit} ·{" "}
                  {humanize(level.sla_type)}
                </p>
              </article>
            ))}
          </div>
        ) : (
          <EmptyState message="No contract-level service levels recorded." />
        )}
      </section>
    </div>
  );
}

export function ContractDetailPage({ id }: { id: string }) {
  const auth = useAuth();
  const companyId = selectedCompany(auth);
  const [contract, setContract] = useState<Contract | null>(null);
  const [error, setError] = useState("");
  const requestId = useRef(0);
  const load = useCallback(() => {
    const request = ++requestId.current;
    getContract(id)
      .then((value) => {
        if (request === requestId.current) {
          setContract(value);
          setError("");
        }
      })
      .catch((reason) => {
        if (request === requestId.current) {
          setContract(null);
          setError(
            reason instanceof ApiError && reason.status === 404
              ? "Contract not found in the selected Company."
              : "Contract could not be loaded.",
          );
        }
      });
  }, [id]);
  useEffect(load, [companyId, load]);
  async function run(action: "submit" | "approve" | "activate") {
    if (!window.confirm(`Confirm ${action} for this contract?`)) return;
    try {
      await contractAction(id, action);
      load();
    } catch (reason) {
      setError(
        reason instanceof ApiError
          ? reason.message
          : "Contract action could not be completed.",
      );
    }
  }
  if (!auth.can("contracts.view_servicecontract"))
    return (
      <ErrorState message="You do not have permission to view contracts." />
    );
  if (error) return <ErrorState message={error} />;
  if (!contract || contract.company !== companyId)
    return <LoadingState label="Loading contract..." />;
  const actions = (
    <div className="quick-actions">
      {auth.can("contracts.change_servicecontract") &&
      contract.status === "DRAFT" ? (
        <>
          <Link
            className="button button-secondary"
            href={`/contracts/${contract.id}/edit`}
          >
            Edit
          </Link>
          <Button type="button" onClick={() => run("submit")}>
            Submit for approval
          </Button>
        </>
      ) : null}
      {auth.can("contracts.approve_contract") &&
      contract.status === "PENDING_APPROVAL" ? (
        <Button type="button" onClick={() => run("approve")}>
          Approve
        </Button>
      ) : null}
      {auth.can("contracts.activate_contract") &&
      contract.status === "APPROVED" ? (
        <Button type="button" onClick={() => run("activate")}>
          Activate
        </Button>
      ) : null}
    </div>
  );
  return (
    <>
      <PageHeader
        title={contract.title}
        description={`Contract ${contract.contract_number}`}
        actions={actions}
      />
      <section className="detail-card">
        <div className="detail-heading">
          <Status value={contract.status} />
        </div>
        <dl className="detail-grid">
          <dt>Client</dt>
          <dd>
            <Link href={`/clients/${contract.client}`}>
              {contract.client_name}
            </Link>
          </dd>
          <dt>Type</dt>
          <dd>{humanize(contract.contract_type)}</dd>
          <dt>Start date</dt>
          <dd>{contract.start_date}</dd>
          <dt>End date</dt>
          <dd>{contract.end_date || "Open ended"}</dd>
          <dt>Currency</dt>
          <dd>{contract.currency}</dd>
          <dt>Client reference</dt>
          <dd>{contract.client_reference || "-"}</dd>
          <dt>Purchase order</dt>
          <dd>{contract.purchase_order_reference || "-"}</dd>
          <dt>Account manager</dt>
          <dd>{contract.account_manager_name || "Unassigned"}</dd>
        </dl>
        {contract.description ? <p>{contract.description}</p> : null}
      </section>
      <ContractPanels contract={contract} />
    </>
  );
}
