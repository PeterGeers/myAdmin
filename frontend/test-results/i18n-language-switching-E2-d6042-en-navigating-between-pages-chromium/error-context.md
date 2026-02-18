# Page snapshot

```yaml
- generic [active] [ref=e1]:
  - generic [ref=e5]:
    - img "myAdmin Logo" [ref=e6]
    - generic [ref=e7]:
      - heading "Welcome to myAdmin" [level=2] [ref=e8]
      - paragraph [ref=e9]: Sign in to access your dashboard
    - generic [ref=e10]:
      - button "Sign in with Cognito" [ref=e11] [cursor=pointer]
      - separator [ref=e12]
      - generic [ref=e13]:
        - paragraph [ref=e14]: Forgot your password?
        - generic [ref=e15] [cursor=pointer]: Reset it here
    - alert [ref=e16]:
      - img [ref=e18]
      - generic [ref=e20]: You will be redirected to a secure login page. After authentication, you'll return to myAdmin.
    - paragraph [ref=e21]: Protected by AWS Cognito
  - generic:
    - region "Notifications-top"
    - region "Notifications-top-left"
    - region "Notifications-top-right"
    - region "Notifications-bottom-left"
    - region "Notifications-bottom"
    - region "Notifications-bottom-right"
```