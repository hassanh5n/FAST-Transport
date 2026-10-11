// One "All / Jadoon / Nadeem" choice shared by every admin page and remembered
// in the browser, plus helpers to filter lists and label rows by contractor.
import { useEffect, useState, useSyncExternalStore } from "react";
import { getContractors } from "../services/transportService";
import { selectStyle } from "../styles/formStyles";
import { colors } from "../theme";

const KEY = "admin.contractor";
const listeners = new Set();
const read = () => { try { return localStorage.getItem(KEY) || ""; } catch { return ""; } };
const subscribe = (fn) => { listeners.add(fn); return () => listeners.delete(fn); };

export function useContractor() {
  const selected = useSyncExternalStore(subscribe, read);
  const [contractors, setContractors] = useState([]);
  useEffect(() => { getContractors().then((res) => setContractors(res.data)).catch(() => {}); }, []);

  const setSelected = (value) => {
    try { localStorage.setItem(KEY, value); } catch { /* private mode: choice lasts this page only */ }
    listeners.forEach((fn) => fn());
  };
  // Rows with no contractor yet stay visible under every filter, so nothing goes missing.
  const matches = (contractorId) => !selected || contractorId == null || String(contractorId) === selected;
  const nameOf = (contractorId) => contractors.find((c) => c.id === contractorId)?.name || "";
  return { selected, setSelected, contractors, matches, nameOf };
}

export function ContractorSwitch({ value }) {
  const { selected, setSelected, contractors } = value;
  return (
    <label style={{ display: "inline-flex", alignItems: "center", gap: 8, fontSize: 13, fontWeight: 600, color: colors.textSecondary, marginBottom: 16 }}>
      Contractor
      <select value={selected} onChange={(e) => setSelected(e.target.value)} style={{ ...selectStyle, width: "auto", minWidth: 140 }}>
        <option value="">All contractors</option>
        {contractors.map((c) => <option key={c.id} value={String(c.id)}>{c.name}</option>)}
      </select>
    </label>
  );
}

// Select for a single record's contractor in add/edit forms.
export function ContractorSelect({ contractors, value, onChange, name = "contractor" }) {
  return (
    <select name={name} value={value ?? ""} onChange={onChange} style={selectStyle}>
      <option value="">No contractor</option>
      {contractors.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
    </select>
  );
}
