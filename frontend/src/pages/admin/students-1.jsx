import { useEffect, useState } from "react";
import PageShell, { PageTitle } from "../../components/PageShell";
import Table from "../../components/Table";
import { getStudents } from "../../services/transportService";

function StudentsPage() {
  const [students, setStudents] = useState([]);

  useEffect(() => {
    getStudents()
      .then((res) => setStudents(res.data))
      .catch(() => alert("Failed to fetch students."));
  }, []);

  const columns = [
    { key: "id", label: "ID" },
    {
      key: "full_name", label: "Full Name",
      render: (row) => {
        const name = `${row.user.first_name || ""} ${row.user.last_name || ""}`.trim();
        return name || row.user.username;
      }
    },
    { key: "username", label: "Username", render: (row) => row.user.username },
    { key: "email", label: "Email", render: (row) => row.user.email },
    { key: "roll_number", label: "Roll Number" },
    { key: "batch", label: "Batch" },
    { key: "department", label: "Department" },
  ];

  return (
    <PageShell role="staff" title="Admin — Students">
      <PageTitle sub="Registered students in the transport system.">All Students</PageTitle>
      <Table columns={columns} rows={students} />
    </PageShell>
  );
}

export default StudentsPage;
