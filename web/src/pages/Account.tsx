import { useState, type FormEvent } from "react";
import { ApiError, api, type Me } from "../api";
import { ErrorBox } from "../components/ui";

/** The shortest password the server accepts (contract 3.4.0, AM-81); the server is the authority and says why it refuses one. */
export const PASSWORD_MIN_LENGTH = 12;

/** What the sign-in form says for a refused sign-in. A wrong name and a wrong password are deliberately one message. */
export function passwordSignInMessage(error: ApiError): string {
  switch (error.code) {
    case "invalid_credentials":
      return "The user name or the password is not right.";
    case "too_many_attempts":
      return error.body?.message ?? "Too many wrong passwords. Try again in a few minutes.";
    case "user_disabled":
      return "This account is disabled. Ask an administrator.";
    case "network":
      return "The server could not be reached. Check your connection and try again.";
    default:
      return "The sign-in did not complete. Please try again.";
  }
}

/** Why a new password cannot be sent yet, checked in the browser before the server is asked; null when it can. */
export function newPasswordProblem(password: string, again: string): string | null {
  if (password.length < PASSWORD_MIN_LENGTH) return `Use at least ${PASSWORD_MIN_LENGTH} characters.`;
  if (password !== again) return "The two entries of the new password differ.";
  return null;
}

/** Sign in with a user name and a password (AUTH_MODE=password, AM-81). */
export function PasswordSignIn({ onSignedIn }: { onSignedIn: (me: Me) => void }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [refused, setRefused] = useState<string | null>(null);
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setRefused(null);
    try {
      onSignedIn(await api.passwordLogin(username.trim(), password));
    } catch (failure) {
      setPassword("");
      setRefused(passwordSignInMessage(failure instanceof ApiError ? failure : new ApiError(0, null)));
    } finally {
      setBusy(false);
    }
  };
  return (
    <form className="account-form" aria-label="Sign in" onSubmit={(event) => void submit(event)}>
      <p className="small">Sign in with your own account. An administrator creates accounts and can give you a new password.</p>
      <label>
        User name
        <input name="username" autoComplete="username" autoCapitalize="none" spellCheck={false} maxLength={100} required autoFocus value={username} onChange={(event) => setUsername(event.target.value)} />
      </label>
      <label>
        Password
        <input name="password" type="password" autoComplete="current-password" maxLength={200} required value={password} onChange={(event) => setPassword(event.target.value)} />
      </label>
      {refused && (
        <p className="error" role="alert">
          {refused}
        </p>
      )}
      <div className="actions">
        <button type="submit" className="primary" disabled={busy || !username.trim() || !password}>
          {busy ? "Signing in..." : "Sign in"}
        </button>
      </div>
    </form>
  );
}

/** Replace your own password, proving the current one. `forced` is the first sign-in with a password an admin set. */
export function ChangePassword({ forced = false, onChanged }: { forced?: boolean; onChanged?: () => void }) {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [again, setAgain] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [done, setDone] = useState(false);
  const problem = next || again ? newPasswordProblem(next, again) : null;
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (newPasswordProblem(next, again)) return;
    setBusy(true);
    setError(null);
    setDone(false);
    try {
      await api.changePassword(current, next);
      setCurrent("");
      setNext("");
      setAgain("");
      setDone(true);
      onChanged?.();
    } catch (failure) {
      setError(failure instanceof ApiError ? failure : new ApiError(0, null));
    } finally {
      setBusy(false);
    }
  };
  return (
    <form className="account-form" aria-label="Change password" onSubmit={(event) => void submit(event)}>
      <label>
        {forced ? "The password you were given" : "Current password"}
        <input name="current-password" type="password" autoComplete="current-password" maxLength={200} required value={current} onChange={(event) => setCurrent(event.target.value)} />
      </label>
      <label>
        New password
        <input name="new-password" type="password" autoComplete="new-password" minLength={PASSWORD_MIN_LENGTH} maxLength={200} required value={next} onChange={(event) => setNext(event.target.value)} />
        <small>At least {PASSWORD_MIN_LENGTH} characters, without your name. A few unrelated words work well.</small>
      </label>
      <label>
        New password, again
        <input name="new-password-again" type="password" autoComplete="new-password" maxLength={200} required value={again} onChange={(event) => setAgain(event.target.value)} />
      </label>
      {problem && <p className="small muted">{problem}</p>}
      {error && <ErrorBox error={error} />}
      {done && (
        <p role="status" className="small">
          Password changed. Your other sessions were signed out.
        </p>
      )}
      <div className="actions">
        <button type="submit" className="primary" disabled={busy || !current || !!newPasswordProblem(next, again)}>
          {busy ? "Saving..." : "Change password"}
        </button>
      </div>
    </form>
  );
}
