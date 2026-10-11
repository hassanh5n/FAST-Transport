import { useEffect, useRef, useState } from "react";
import { colors, fonts, radius, shadow } from "../theme";
import {
  getNotifications,
  markNotificationRead,
  markAllNotificationsRead,
  deleteNotification,
  clearAllNotifications,
} from "../services/transportService";

const POLL_INTERVAL_MS = 60000; // a new notification shows within a minute; opening the bell refreshes at once

function timeAgo(dateString) {
  const diffMs = Date.now() - new Date(dateString).getTime();
  const mins = Math.floor(diffMs / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

function NotificationBell() {
  const [notifications, setNotifications] = useState([]);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const containerRef = useRef(null);

  // The API is owner-scoped server-side, so whatever comes back already
  // belongs to this user — no client-side username filtering needed.
  const fetchNotifications = () =>
    getNotifications()
      .then((res) => setNotifications(res.data))
      .catch(() => {}); // silent — the bell just stays as-is if this fails

  useEffect(() => {
    fetchNotifications();
    // Skip polls while the tab is hidden; catch up as soon as it is shown again.
    const interval = setInterval(() => { if (!document.hidden) fetchNotifications(); }, POLL_INTERVAL_MS);
    const onShow = () => { if (!document.hidden) fetchNotifications(); };
    document.addEventListener("visibilitychange", onShow);
    return () => { clearInterval(interval); document.removeEventListener("visibilitychange", onShow); };
  }, []);

  // Close dropdown on outside click
  useEffect(() => {
    function handleClick(e) {
      if (containerRef.current && !containerRef.current.contains(e.target)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  const sorted = [...notifications].sort(
    (a, b) => new Date(b.created_at) - new Date(a.created_at)
  );
  const unreadCount = notifications.filter((n) => !n.is_read).length;

  // ── Actions ───────────────────────────────────────────────────────────────
  // Each updates local state optimistically so the dropdown feels instant,
  // and falls back to server truth if the request fails.

  const handleMarkRead = async (n) => {
    if (n.is_read) return;
    setNotifications((prev) =>
      prev.map((x) => (x.id === n.id ? { ...x, is_read: true } : x))
    );
    try {
      await markNotificationRead(n.id);
    } catch {
      fetchNotifications();
    }
  };

  const handleMarkAllRead = async () => {
    if (unreadCount === 0 || busy) return;
    setBusy(true);
    setNotifications((prev) => prev.map((x) => ({ ...x, is_read: true })));
    try {
      await markAllNotificationsRead();
    } catch {
      fetchNotifications();
    } finally {
      setBusy(false);
    }
  };

  const handleDelete = async (e, n) => {
    e.stopPropagation(); // don't also trigger mark-as-read on the row
    const previous = notifications;
    setNotifications((prev) => prev.filter((x) => x.id !== n.id));
    try {
      await deleteNotification(n.id);
    } catch {
      setNotifications(previous);
    }
  };

  const handleClearAll = async () => {
    if (notifications.length === 0 || busy) return;
    if (!window.confirm("Clear all notifications? This cannot be undone.")) return;
    setBusy(true);
    const previous = notifications;
    setNotifications([]);
    try {
      await clearAllNotifications();
    } catch {
      setNotifications(previous);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div ref={containerRef} style={{ position: "relative" }}>
      <button
        onClick={() => { if (!open) fetchNotifications(); setOpen((o) => !o); }}
        style={styles.bellBtn}
        aria-label="Notifications"
      >
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M18 8a6 6 0 0 0-12 0c0 7-3 9-3 9h18s-3-2-3-9" />
          <path d="M13.73 21a2 2 0 0 1-3.46 0" />
        </svg>
        {unreadCount > 0 && (
          <span style={styles.badge}>{unreadCount > 9 ? "9+" : unreadCount}</span>
        )}
      </button>

      {open && (
        <div style={styles.dropdown}>
          <div style={styles.dropdownHeader}>
            <span style={styles.headerTitle}>
              Notifications
              {unreadCount > 0 && (
                <span style={styles.headerCount}>{unreadCount} new</span>
              )}
            </span>
            <div style={styles.headerActions}>
              <button
                onClick={handleMarkAllRead}
                disabled={unreadCount === 0 || busy}
                style={{
                  ...styles.headerBtn,
                  ...(unreadCount === 0 || busy ? styles.headerBtnDisabled : {}),
                }}
              >
                Mark all read
              </button>
              <button
                onClick={handleClearAll}
                disabled={notifications.length === 0 || busy}
                style={{
                  ...styles.headerBtn,
                  ...styles.headerBtnDanger,
                  ...(notifications.length === 0 || busy
                    ? styles.headerBtnDisabled
                    : {}),
                }}
              >
                Clear all
              </button>
            </div>
          </div>

          <div style={styles.list}>
            {sorted.length === 0 && (
              <div style={styles.empty}>No notifications yet.</div>
            )}
            {sorted.slice(0, 30).map((n) => (
              <div
                key={n.id}
                onClick={() => handleMarkRead(n)}
                title={n.is_read ? "" : "Click to mark as read"}
                style={{
                  ...styles.item,
                  background: n.is_read ? "#fff" : colors.accentGlow,
                  borderLeft:
                    n.type === "alert"
                      ? "3px solid #dc2626"
                      : n.is_read
                        ? "3px solid transparent"
                        : `3px solid ${colors.accent}`,
                  cursor: n.is_read ? "default" : "pointer",
                }}
              >
                <div style={styles.itemHead}>
                  <div style={styles.itemTitle}>
                    {!n.is_read && <span style={styles.unreadDot} />}
                    {n.title}
                  </div>
                  <button
                    onClick={(e) => handleDelete(e, n)}
                    style={styles.dismissBtn}
                    aria-label="Remove notification"
                    title="Remove"
                  >
                    ×
                  </button>
                </div>
                <div style={styles.itemMessage}>{n.message}</div>
                <div style={styles.itemTime}>{timeAgo(n.created_at)}</div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

const styles = {
  bellBtn: {
    position: "relative",
    background: "transparent",
    border: `1px solid ${colors.borderLight}`,
    borderRadius: "9px",
    padding: "7px",
    cursor: "pointer",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    color: colors.textSecondary,
  },
  badge: {
    position: "absolute",
    top: "-4px",
    right: "-4px",
    background: "#dc2626",
    color: "#fff",
    fontSize: "10px",
    fontWeight: "700",
    borderRadius: "999px",
    minWidth: "16px",
    height: "16px",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    padding: "0 3px",
    lineHeight: 1,
  },
  dropdown: {
    position: "absolute",
    top: "calc(100% + 8px)",
    right: 0,
    width: "360px",
    maxWidth: "90vw",
    background: "#fff",
    border: `1px solid ${colors.borderLight}`,
    borderRadius: radius.lg,
    boxShadow: shadow.navbar || "0 8px 24px rgba(11,45,66,0.14)",
    zIndex: 300,
    overflow: "hidden",
    fontFamily: fonts.body,
  },
  dropdownHeader: {
    padding: "11px 14px",
    borderBottom: `1px solid ${colors.borderLight}`,
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: "8px",
    flexWrap: "wrap",
    background: colors.tableHeaderBg,
  },
  headerTitle: {
    fontWeight: "700",
    fontSize: "13px",
    color: colors.textPrimary,
    display: "inline-flex",
    alignItems: "center",
    gap: "7px",
  },
  headerCount: {
    background: colors.accent,
    color: "#fff",
    fontSize: "10px",
    fontWeight: "700",
    padding: "2px 7px",
    borderRadius: "999px",
    textTransform: "uppercase",
    letterSpacing: "0.03em",
  },
  headerActions: {
    display: "flex",
    gap: "6px",
  },
  headerBtn: {
    background: "transparent",
    border: "none",
    padding: "3px 6px",
    fontSize: "11.5px",
    fontWeight: "600",
    color: colors.accent,
    cursor: "pointer",
    borderRadius: "6px",
    fontFamily: fonts.body,
  },
  headerBtnDanger: {
    color: colors.dangerText,
  },
  headerBtnDisabled: {
    color: colors.textMuted,
    cursor: "default",
  },
  list: {
    maxHeight: "380px",
    overflowY: "auto",
  },
  empty: {
    padding: "26px 16px",
    fontSize: "13px",
    color: colors.textMuted,
    textAlign: "center",
  },
  item: {
    padding: "10px 12px 10px 14px",
    borderBottom: `1px solid ${colors.borderLight}`,
    transition: "background 0.12s",
  },
  itemHead: {
    display: "flex",
    alignItems: "flex-start",
    justifyContent: "space-between",
    gap: "8px",
  },
  itemTitle: {
    fontSize: "13px",
    fontWeight: "600",
    color: colors.textPrimary,
    display: "flex",
    alignItems: "center",
    gap: "6px",
    lineHeight: 1.35,
  },
  unreadDot: {
    width: "7px",
    height: "7px",
    borderRadius: "50%",
    background: colors.accent,
    flexShrink: 0,
  },
  dismissBtn: {
    background: "transparent",
    border: "none",
    color: colors.textMuted,
    fontSize: "17px",
    lineHeight: 1,
    padding: "0 2px",
    cursor: "pointer",
    flexShrink: 0,
    fontFamily: fonts.body,
  },
  itemMessage: {
    fontSize: "12.5px",
    color: colors.textSecondary,
    marginTop: "3px",
    lineHeight: 1.5,
  },
  itemTime: {
    fontSize: "11px",
    color: colors.textMuted,
    marginTop: "4px",
  },
};

export default NotificationBell;
