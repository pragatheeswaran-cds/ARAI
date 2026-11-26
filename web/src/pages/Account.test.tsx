import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, api, type Me } from "../api";
import { ChangePassword, PasswordSignIn, newPasswordProblem, passwordSignInMessage } from "./Account";
import { eventDetail } from "./People";

const me = (over: Partial<Me> = {}): Me => ({
  user_id: "usr-1", display_name: "Asha", email: null, roles: ["reviewer"], permissions: ["read", "export", "review"], auth_mode: "password", csrf_token: "c",
  session_expires_at: null, idle_minutes: 60, sso_logout_url: null, status: "active", created_at: null, last_sign_in_at: null, must_change_password: false, ...over,
});
const refusal = (status: number, error_code: string, message = "") => new ApiError(status, { error_code, message, request_id: "r", details: [] });

afterEach(() => vi.restoreAllMocks());

describe("sign in with a password (AM-81)", () => {
  it("sends the user name and the password and hands over the signed-in person", async () => {
    const login = vi.spyOn(api, "passwordLogin").mockResolvedValue(me());
    const signedIn = vi.fn();
    render(<PasswordSignIn onSignedIn={signedIn} />);
    const button = screen.getByRole("button", { name: "Sign in" });
    expect(button).toBeDisabled();
    await userEvent.type(screen.getByLabelText("User name"), " asha ");
    await userEvent.type(screen.getByLabelText("Password"), "a long passphrase 42");
    await userEvent.click(button);
    expect(login).toHaveBeenCalledWith("asha", "a long passphrase 42");
    await waitFor(() => expect(signedIn).toHaveBeenCalledWith(me()));
  });
  it("keeps the password out of the page: a password field, cleared after a refusal", async () => {
    vi.spyOn(api, "passwordLogin").mockRejectedValue(refusal(401, "invalid_credentials"));
    render(<PasswordSignIn onSignedIn={() => {}} />);
    const password = screen.getByLabelText("Password") as HTMLInputElement;
    expect(password.type).toBe("password");
    expect(password.autocomplete).toBe("current-password");
    await userEvent.type(screen.getByLabelText("User name"), "asha");
    await userEvent.type(password, "not the password");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("The user name or the password is not right.");
    expect(password.value).toBe("");
    expect(document.body.textContent).not.toContain("not the password");
  });
  it("says the same thing for a wrong name and a wrong password, and says when an account is locked or disabled", () => {
    expect(passwordSignInMessage(refusal(401, "invalid_credentials", "anything the server says"))).toBe("The user name or the password is not right.");
    expect(passwordSignInMessage(refusal(429, "too_many_attempts", "Too many wrong passwords. Try again in 5 minutes."))).toMatch(/5 minutes/);
    expect(passwordSignInMessage(refusal(403, "user_disabled"))).toMatch(/disabled/);
    expect(passwordSignInMessage(new ApiError(0, null))).toMatch(/did not complete/);
  });
});

describe("change your password (AM-81)", () => {
  it("checks length and the repeated entry before asking the server", () => {
    expect(newPasswordProblem("short", "short")).toMatch(/at least 12/);
    expect(newPasswordProblem("a long passphrase 42", "a long passphrase 43")).toMatch(/differ/);
    expect(newPasswordProblem("a long passphrase 42", "a long passphrase 42")).toBeNull();
  });
  it("sends the current and the new password once both entries agree, and reports the result", async () => {
    const change = vi.spyOn(api, "changePassword").mockResolvedValue(null);
    const changed = vi.fn();
    render(<ChangePassword forced onChanged={changed} />);
    const button = screen.getByRole("button", { name: "Change password" });
    await userEvent.type(screen.getByLabelText("The password you were given"), "passed on by phone");
    await userEvent.type(screen.getByLabelText(/^New password(?!,)/), "a long passphrase 42");
    await userEvent.type(screen.getByLabelText("New password, again"), "a long passphrase 4");
    expect(button).toBeDisabled();
    expect(screen.getByText("The two entries of the new password differ.")).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("New password, again"), "2");
    await userEvent.click(button);
    expect(change).toHaveBeenCalledWith("passed on by phone", "a long passphrase 42");
    await waitFor(() => expect(changed).toHaveBeenCalled());
    expect(screen.getByRole("status")).toHaveTextContent("Password changed");
  });
  it("shows the server's reason when it refuses the new password", async () => {
    vi.spyOn(api, "changePassword").mockRejectedValue(refusal(422, "weak_password", "The password must not contain the account's name."));
    render(<ChangePassword />);
    await userEvent.type(screen.getByLabelText("Current password"), "passed on by phone");
    await userEvent.type(screen.getByLabelText(/^New password(?!,)/), "asha asha asha asha");
    await userEvent.type(screen.getByLabelText("New password, again"), "asha asha asha asha");
    await userEvent.click(screen.getByRole("button", { name: "Change password" }));
    expect(await screen.findByText(/must not contain the account's name/)).toBeInTheDocument();
  });
});

describe("the sign-in log for accounts with a password", () => {
  it("says who created an account, who reset a password and when an account was locked", () => {
    expect(eventDetail({ kind: "user_created", detail: { by: "u1", by_name: "Admin", roles: ["reviewer"] } })).toBe("by Admin / roles: reviewer");
    expect(eventDetail({ kind: "user_created", detail: { by_name: "configuration", roles: ["admin"], from: "development login" } })).toBe(
      "by configuration / roles: admin / was a persona of the development login",
    );
    expect(eventDetail({ kind: "password_reset", detail: { by: "u1", by_name: "Admin", sessions_ended: 1 } })).toBe("by Admin / 1 session ended");
    expect(eventDetail({ kind: "password_changed", detail: { sessions_ended: 0 } })).toBe("");
    expect(eventDetail({ kind: "refused", detail: { status: 401, reason: "invalid_credentials", locked_minutes: 5 } })).toBe(
      "401 / invalid credentials / account locked for 5 minutes",
    );
    expect(eventDetail({ kind: "sign_in", detail: { mode: "password" } })).toBe("password");
  });
});
