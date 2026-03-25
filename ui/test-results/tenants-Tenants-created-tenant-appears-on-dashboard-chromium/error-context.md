# Page snapshot

```yaml
- generic [active] [ref=e1]:
  - generic [ref=e2]:
    - banner [ref=e3]:
      - generic [ref=e4]:
        - generic [ref=e5]:
          - img [ref=e6]
          - generic [ref=e10]: Haven Platform
        - generic [ref=e11]:
          - generic [ref=e12]: admin@haven.dev
          - link "Sign out" [ref=e13] [cursor=pointer]:
            - /url: /api/auth/signout
            - img [ref=e14]
            - text: Sign out
    - main [ref=e17]:
      - generic [ref=e18]:
        - generic [ref=e19]:
          - heading "Tenants" [level=1] [ref=e20]
          - paragraph [ref=e21]: 0 tenants registered
        - link "New Tenant" [ref=e22] [cursor=pointer]:
          - /url: /tenants/new
          - img [ref=e23]
          - text: New Tenant
      - generic [ref=e24]:
        - img [ref=e25]
        - paragraph [ref=e29]: No tenants yet
        - paragraph [ref=e30]: Create your first tenant to get started.
  - alert [ref=e31]
```