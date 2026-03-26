import type { NextAuthOptions } from "next-auth";
import KeycloakProvider from "next-auth/providers/keycloak";
import GitHubProvider from "next-auth/providers/github";

const providers: NextAuthOptions["providers"] = [
  KeycloakProvider({
    clientId: process.env.KEYCLOAK_CLIENT_ID!,
    clientSecret: process.env.KEYCLOAK_CLIENT_SECRET!,
    issuer: `${process.env.KEYCLOAK_URL}/realms/${process.env.KEYCLOAK_REALM}`,
  }),
];

// GitHub OAuth is optional — only enabled when credentials are configured
if (process.env.GITHUB_ID && process.env.GITHUB_SECRET) {
  providers.push(
    GitHubProvider({
      clientId: process.env.GITHUB_ID,
      clientSecret: process.env.GITHUB_SECRET,
      authorization: { params: { scope: "read:user user:email repo" } },
    })
  );
}

export const authOptions: NextAuthOptions = {
  providers,
  callbacks: {
    async jwt({ token, account }) {
      // Persist access token for API calls
      if (account?.access_token) {
        token.accessToken = account.access_token;
        token.provider = account.provider;
      }
      return token;
    },
    async session({ session, token }) {
      const s = session as typeof session & { accessToken: string; provider: string };
      s.accessToken = token.accessToken as string;
      s.provider = token.provider as string;
      return session;
    },
  },
  pages: {
    signIn: "/auth/signin",
  },
};
