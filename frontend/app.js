const config = window.LEANSTOCK_CONFIG || {};
const storageKey = "leanstock-demo-state";

function isLocalApiUrl(value) {
  return /^https?:\/\/(localhost|127\.0\.0\.1)(:\d+)?$/i.test(value || "");
}

function isLocalFrontend() {
  return ["localhost", "127.0.0.1", ""].includes(window.location.hostname);
}

function deployedApiBaseUrl() {
  const { protocol, hostname } = window.location;
  if (!hostname.endsWith(".kazi.rocks")) {
    return "";
  }
  const apiHost = hostname.endsWith("-frontend.kazi.rocks")
    ? hostname.replace("-frontend.kazi.rocks", "-api.kazi.rocks")
    : hostname.replace(".kazi.rocks", "-api.kazi.rocks");
  return `${protocol}//${apiHost}`;
}

function cleanApiBaseUrl(value) {
  let raw = (value || "").trim();
  if (!raw) {
    return "";
  }
  if (/^[a-z0-9.-]+\.kazi\.rocks(\/.*)?$/i.test(raw)) {
    raw = `https://${raw}`;
  }
  try {
    const url = new URL(raw);
    if (url.hostname.endsWith(".kazi.rocks") && window.location.protocol === "https:") {
      url.protocol = "https:";
    }
    if (url.pathname === "/health" || url.pathname === "/health/") {
      url.pathname = "";
    }
    url.search = "";
    url.hash = "";
    return url.toString().replace(/\/$/, "");
  } catch {
    return raw.replace(/\/+$/, "");
  }
}

function resolveApiBaseUrl(value) {
  // On kazi.rocks, always auto-generate the API URL from the hostname.
  // This avoids relying on API_BASE_URL being set correctly in the container env.
  const deployed = deployedApiBaseUrl();
  if (deployed) return deployed;
  // Local / custom environments: use the configured value or fallback.
  const configured = cleanApiBaseUrl(value);
  if (configured && (!isLocalApiUrl(configured) || isLocalFrontend())) {
    return configured;
  }
  return configured || "http://localhost:8000";
}

const state = {
  apiBaseUrl: resolveApiBaseUrl(config.apiBaseUrl),
  accessToken: "",
  refreshToken: "",
  tenantAdminAccessToken: "",
  managerAccessToken: "",
  user: null,
  ...JSON.parse(localStorage.getItem(storageKey) || "{}")
};

state.apiBaseUrl = resolveApiBaseUrl(state.apiBaseUrl);

const $ = (id) => document.getElementById(id);

function saveState() {
  localStorage.setItem(storageKey, JSON.stringify(state));
  renderSession();
}

function setValue(id, value) {
  const input = $(id);
  if (input && value !== undefined && value !== null) {
    input.value = value;
  }
}

function getValue(id) {
  return $(id).value.trim();
}

function numberValue(id) {
  return Number(getValue(id));
}

function output(payload, label = "Response") {
  $("output").textContent = `${label}\n${JSON.stringify(payload, null, 2)}`;
}

function renderSession() {
  $("apiBaseUrl").value = state.apiBaseUrl;
  $("managerAccessToken").value = state.managerAccessToken || "";
  $("sessionSummary").textContent = state.user
    ? `${state.user.email} | ${state.user.role} | verified: ${Boolean(state.user.email_verified_at)}`
    : state.accessToken
      ? "Token saved, user not loaded"
      : "No active session";
  $("swaggerLink").href = `${state.apiBaseUrl}/docs`;
}

async function api(path, options = {}) {
  const headers = {
    ...(options.headers || {})
  };
  if (options.body !== undefined) {
    headers["Content-Type"] = "application/json";
  }
  const token = options.token === undefined ? state.accessToken : options.token;
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }

  const response = await fetch(`${state.apiBaseUrl}${path}`, {
    ...options,
    headers,
    body: options.body !== undefined ? JSON.stringify(options.body) : undefined
  });
  const text = await response.text();
  const payload = text ? JSON.parse(text) : {};
  if (!response.ok) {
    const error = new Error(payload.message || `HTTP ${response.status}`);
    error.payload = payload;
    error.status = response.status;
    throw error;
  }
  return payload;
}

async function run(label, fn) {
  try {
    const result = await fn();
    output(result, label);
    return result;
  } catch (error) {
    output(error.payload || { message: error.message, status: error.status }, `${label} failed`);
    return error.payload || null;
  }
}

async function loadMe() {
  const me = await api("/v1/auth/me");
  state.user = me;
  saveState();
  return me;
}

function authBody(role = "tenant_admin") {
  const body = {
    email: getValue("authEmail"),
    password: getValue("authPassword"),
    name: getValue("authName"),
    role
  };
  if (role === "tenant_admin") {
    body.tenant_name = "Arzan Shop";
    body.tenant_slug = getValue("tenantSlug");
  }
  return body;
}

function compactPatch(fields) {
  const body = {};
  for (const [key, value] of Object.entries(fields)) {
    if (value === undefined || value === null) continue;
    if (typeof value === "string" && value.trim() === "") continue;
    if (typeof value === "number" && Number.isNaN(value)) continue;
    body[key] = value;
  }
  return body;
}

function numberValueOrUndefined(id) {
  const raw = getValue(id);
  if (raw === "") return undefined;
  const num = Number(raw);
  return Number.isNaN(num) ? undefined : num;
}

function productBody(sku = getValue("sku")) {
  return {
    name: getValue("productName"),
    category: "Clothing",
    unit_of_measure: "pcs",
    variants: [
      {
        sku,
        color: "Red",
        size: "L",
        barcode: `${Date.now()}`.slice(-12),
        cost_price: 2100,
        selling_price: 4990,
        liquidation_floor_price: 2990
      }
    ]
  };
}

document.addEventListener("DOMContentLoaded", () => {
  renderSession();

  $("saveApiBase").addEventListener("click", () => {
    state.apiBaseUrl = resolveApiBaseUrl(getValue("apiBaseUrl"));
    saveState();
    output({ apiBaseUrl: state.apiBaseUrl }, "Saved API base URL");
  });

  $("healthCheck").addEventListener("click", () => run("Health", () => api("/health", { token: "" })));

  $("registerTenant").addEventListener("click", () =>
    run("Register Tenant Admin", () => api("/v1/auth/register", { method: "POST", token: "", body: authBody() }))
  );

  $("verifyEmail").addEventListener("click", () =>
    run("Verify Email", () =>
      api("/v1/auth/verify-email", {
        method: "POST",
        token: "",
        body: { token: getValue("verificationToken"), email: getValue("authEmail") }
      })
    )
  );

  $("resendVerification").addEventListener("click", () =>
    run("Resend Verification", () =>
      api("/v1/auth/resend-verification", {
        method: "POST",
        token: "",
        body: { email: getValue("authEmail") }
      })
    )
  );

  $("login").addEventListener("click", () =>
    run("Login", async () => {
      const tokens = await api("/v1/auth/login", {
        method: "POST",
        token: "",
        body: { email: getValue("authEmail"), password: getValue("authPassword") }
      });
      state.accessToken = tokens.access_token;
      state.tenantAdminAccessToken = tokens.access_token;
      state.refreshToken = tokens.refresh_token;
      saveState();
      await loadMe();
      return tokens;
    })
  );

  $("me").addEventListener("click", () => run("Me", loadMe));

  $("refresh").addEventListener("click", () =>
    run("Refresh", async () => {
      const tokens = await api("/v1/auth/refresh", {
        method: "POST",
        token: "",
        body: { refresh_token: state.refreshToken }
      });
      state.accessToken = tokens.access_token;
      state.tenantAdminAccessToken = tokens.access_token;
      state.refreshToken = tokens.refresh_token;
      saveState();
      return tokens;
    })
  );

  $("logout").addEventListener("click", () =>
    run("Logout", async () => {
      await api("/v1/auth/logout", {
        method: "POST",
        body: { refresh_token: state.refreshToken }
      });
      state.accessToken = "";
      state.refreshToken = "";
      state.user = null;
      saveState();
      return { message: "Logged out" };
    })
  );

  $("requestPasswordReset").addEventListener("click", () =>
    run("Request Password Reset", () =>
      api("/v1/auth/password-reset/request", {
        method: "POST",
        token: "",
        body: { email: getValue("authEmail") }
      })
    )
  );

  $("confirmPasswordReset").addEventListener("click", () =>
    run("Confirm Password Reset", () =>
      api("/v1/auth/password-reset/confirm", {
        method: "POST",
        token: "",
        body: {
          token: getValue("passwordResetToken"),
          new_password: "N3wSecur3P@ss!"
        }
      })
    )
  );

  $("registerManager").addEventListener("click", () =>
    run("Register Manager", () =>
      api("/v1/auth/register", {
        method: "POST",
        body: {
          email: getValue("managerEmail"),
          password: "Secur3P@ss!",
          name: "Warehouse Manager",
          role: "warehouse_manager"
        }
      })
    )
  );

  $("verifyManager").addEventListener("click", () =>
    run("Verify Manager", () =>
      api("/v1/auth/verify-email", {
        method: "POST",
        token: "",
        body: { token: getValue("managerVerificationToken"), email: getValue("managerEmail") }
      })
    )
  );

  $("loginManager").addEventListener("click", () =>
    run("Login Manager", async () => {
      const tokens = await api("/v1/auth/login", {
        method: "POST",
        token: "",
        body: { email: getValue("managerEmail"), password: "Secur3P@ss!" }
      });
      state.managerAccessToken = tokens.access_token;
      setValue("managerAccessToken", tokens.access_token);
      saveState();
      return tokens;
    })
  );

  $("managerForbiddenProduct").addEventListener("click", () =>
    run("Manager Create Product 403", () =>
      api("/v1/products", {
        method: "POST",
        token: state.managerAccessToken || getValue("managerAccessToken"),
        body: productBody(`FORBIDDEN-${Date.now()}`)
      })
    )
  );

  $("createWarehouseA").addEventListener("click", () =>
    run("Create Warehouse A", async () => {
      const result = await api("/v1/warehouses", {
        method: "POST",
        body: { name: getValue("warehouseAName"), location: "Almaty" }
      });
      setValue("sourceWarehouseId", result.id);
      return result;
    })
  );

  $("createWarehouseB").addEventListener("click", () =>
    run("Create Warehouse B", async () => {
      const result = await api("/v1/warehouses", {
        method: "POST",
        body: { name: getValue("warehouseBName"), location: "Astana" }
      });
      setValue("destinationWarehouseId", result.id);
      return result;
    })
  );

  $("updateWarehouseA").addEventListener("click", () =>
    run("Update Warehouse A", () => {
      const body = compactPatch({
        name: getValue("warehouseUpdateName"),
        location: getValue("warehouseUpdateLocation")
      });
      if (Object.keys(body).length === 0) {
        return Promise.reject(
          Object.assign(new Error("Fill at least one update field"), {
            payload: { message: "Provide a new name or location to update." }
          })
        );
      }
      return api(`/v1/warehouses/${getValue("sourceWarehouseId")}`, {
        method: "PATCH",
        body
      });
    })
  );

  $("listWarehouses").addEventListener("click", () =>
    run("List Warehouses", () => api("/v1/warehouses?limit=50"))
  );

  $("createProduct").addEventListener("click", () =>
    run("Create Product", async () => {
      const result = await api("/v1/products", { method: "POST", body: productBody() });
      setValue("productId", result.id);
      setValue("variantId", result.variants[0].id);
      return result;
    })
  );

  $("updateProduct").addEventListener("click", () =>
    run("Update Product", () => {
      const body = compactPatch({
        name: getValue("productUpdateName"),
        category: getValue("productUpdateCategory")
      });
      if (Object.keys(body).length === 0) {
        return Promise.reject(
          Object.assign(new Error("Fill at least one update field"), {
            payload: { message: "Provide a new name or category to update." }
          })
        );
      }
      return api(`/v1/products/${getValue("productId")}`, {
        method: "PATCH",
        body
      });
    })
  );

  $("updateVariant").addEventListener("click", () =>
    run("Update Variant", () => {
      const body = compactPatch({
        color: getValue("variantUpdateColor"),
        size: getValue("variantUpdateSize"),
        selling_price: numberValueOrUndefined("variantUpdateSellingPrice"),
        liquidation_floor_price: numberValueOrUndefined("variantUpdateFloorPrice")
      });
      if (Object.keys(body).length === 0) {
        return Promise.reject(
          Object.assign(new Error("Fill at least one update field"), {
            payload: { message: "Provide at least one variant field to update." }
          })
        );
      }
      return api(`/v1/products/variants/${getValue("variantId")}`, {
        method: "PATCH",
        body
      });
    })
  );

  $("listProducts").addEventListener("click", () => run("List Products", () => api("/v1/products")));
  $("getProduct").addEventListener("click", () =>
    run("Get Product", () => api(`/v1/products/${getValue("productId")}`))
  );

  $("adjustInventory").addEventListener("click", () =>
    run("Adjust Inventory", () =>
      api("/v1/inventory/adjust", {
        method: "POST",
        body: {
          variant_id: getValue("variantId"),
          warehouse_id: getValue("sourceWarehouseId"),
          quantity_delta: numberValue("adjustQuantity"),
          reason: "surplus",
          note: "Frontend demo adjustment"
        }
      })
    )
  );

  $("listInventory").addEventListener("click", () => run("List Inventory", () => api("/v1/inventory")));

  $("reserveInventory").addEventListener("click", () =>
    run("Reserve Inventory", () =>
      api("/v1/inventory/reserve", {
        method: "POST",
        body: {
          variant_id: getValue("variantId"),
          warehouse_id: getValue("sourceWarehouseId"),
          quantity: numberValue("reserveQuantity"),
          order_reference: getValue("orderReference")
        }
      })
    )
  );

  $("forecast").addEventListener("click", () =>
    run("Forecast", () =>
      api(`/v1/inventory/forecast?warehouse_id=${getValue("sourceWarehouseId")}&lead_time_days=${numberValue("leadTimeDays")}&reorder_only=false`)
    )
  );

  $("createTransfer").addEventListener("click", () =>
    run("Create Transfer", async () => {
      const result = await api("/v1/transfers", {
        method: "POST",
        body: {
          request_id: getValue("transferRequestId"),
          from_warehouse_id: getValue("sourceWarehouseId"),
          to_warehouse_id: getValue("destinationWarehouseId"),
          variant_id: getValue("variantId"),
          quantity: numberValue("transferQuantity"),
          note: "Frontend transfer demo"
        }
      });
      setValue("transferId", result.id);
      return result;
    })
  );

  $("confirmTransfer").addEventListener("click", () =>
    run("Confirm Transfer", () =>
      api(`/v1/transfers/${getValue("transferId")}/confirm`, {
        method: "POST",
        body: { received_quantity: numberValue("transferQuantity") }
      })
    )
  );

  $("createCancelTransfer").addEventListener("click", () =>
    run("Create Transfer For Cancel", async () => {
      const result = await api("/v1/transfers", {
        method: "POST",
        body: {
          request_id: `${getValue("transferRequestId")}-cancel`,
          from_warehouse_id: getValue("sourceWarehouseId"),
          to_warehouse_id: getValue("destinationWarehouseId"),
          variant_id: getValue("variantId"),
          quantity: 1,
          note: "Frontend cancel transfer demo"
        }
      });
      setValue("cancelTransferId", result.id);
      return result;
    })
  );

  $("cancelTransfer").addEventListener("click", () =>
    run("Cancel Transfer", () =>
      api(`/v1/transfers/${getValue("cancelTransferId")}/cancel`, { method: "POST" })
    )
  );

  $("listTransfers").addEventListener("click", () => run("List Transfers", () => api("/v1/transfers")));

  $("createSupplier").addEventListener("click", () =>
    run("Create Supplier", async () => {
      const result = await api("/v1/suppliers", {
        method: "POST",
        body: {
          name: getValue("supplierName"),
          contact_email: getValue("supplierEmail"),
          phone: "+77001234567",
          lead_time_days: numberValue("supplierLeadTime")
        }
      });
      setValue("supplierId", result.id);
      return result;
    })
  );

  $("updateSupplier").addEventListener("click", () =>
    run("Update Supplier", () => {
      const body = compactPatch({
        name: getValue("supplierUpdateName"),
        contact_email: getValue("supplierUpdateEmail"),
        phone: getValue("supplierUpdatePhone"),
        lead_time_days: numberValueOrUndefined("supplierUpdateLeadTime")
      });
      if (Object.keys(body).length === 0) {
        return Promise.reject(
          Object.assign(new Error("Fill at least one update field"), {
            payload: { message: "Provide at least one supplier field to update." }
          })
        );
      }
      return api(`/v1/suppliers/${getValue("supplierId")}`, {
        method: "PATCH",
        body
      });
    })
  );

  $("listSuppliers").addEventListener("click", () => run("List Suppliers", () => api("/v1/suppliers")));

  $("createPurchaseOrder").addEventListener("click", () =>
    run("Create Purchase Order", async () => {
      const result = await api("/v1/purchase-orders", {
        method: "POST",
        body: {
          po_number: getValue("poNumber"),
          supplier_id: getValue("supplierId"),
          warehouse_id: getValue("sourceWarehouseId"),
          variant_id: getValue("variantId"),
          quantity: numberValue("poQuantity"),
          expected_unit_cost: numberValue("poUnitCost")
        }
      });
      setValue("purchaseOrderId", result.id);
      return result;
    })
  );

  $("submitPurchaseOrder").addEventListener("click", () =>
    run("Submit Purchase Order", () =>
      api(`/v1/purchase-orders/${getValue("purchaseOrderId")}/submit`, { method: "POST" })
    )
  );

  $("confirmPurchaseOrder").addEventListener("click", () =>
    run("Confirm Purchase Order", () =>
      api(`/v1/purchase-orders/${getValue("purchaseOrderId")}/confirm`, { method: "POST" })
    )
  );

  $("receivePurchaseOrder").addEventListener("click", () =>
    run("Receive Purchase Order", () =>
      api(`/v1/purchase-orders/${getValue("purchaseOrderId")}/receive`, {
        method: "POST",
        body: { received_quantity: numberValue("poQuantity") }
      })
    )
  );

  $("listPurchaseOrders").addEventListener("click", () =>
    run("List Purchase Orders", () => api("/v1/purchase-orders"))
  );

  $("listEmailJobs").addEventListener("click", () =>
    run("List Email Jobs", () => api("/v1/admin/email-jobs"))
  );

  $("listAuditLogs").addEventListener("click", () =>
    run("List Audit Logs", () => api("/v1/admin/audit-logs?limit=50"))
  );

  $("triggerDecay").addEventListener("click", () =>
    run("Trigger Decay", () => api("/v1/admin/decay/run", { method: "POST" }))
  );
});
