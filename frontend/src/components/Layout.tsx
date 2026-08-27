import { Link, Outlet } from "react-router-dom";
import ChatWidget from "./ChatWidget";
import { useAuth } from "../context/AuthContext";
import "./layout.css";

export default function Layout() {
  const { user, logout } = useAuth();

  return (
    <div className="app-shell">
      <header className="app-header">
        <div className="container app-header-inner">
          <Link to="/projects" className="app-brand">
            Layout Builder
          </Link>
          {user && (
            <div className="app-header-user">
              <span className="muted">{user.email}</span>
              <button className="btn btn-secondary" onClick={logout}>
                Log out
              </button>
            </div>
          )}
        </div>
      </header>
      <main className="app-main container">
        <Outlet />
      </main>
      {user && <ChatWidget />}
    </div>
  );
}
