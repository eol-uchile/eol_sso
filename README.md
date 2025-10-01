# EOL_SSO

Acts as a middleware between apps and the interface of uchileedxlogin and the models of eol_sso_login. In order to work it requires either uchileedxlogin or eol_sso_login to be installed alongside it.

## TESTS

This repository includes tests that verify the functionality of the middleware's integration with both uchileedxlogin and eol_sso_login.

**Prepare tests:**

- Install **act** following the instructions in [https://nektosact.com/installation/index.html](https://nektosact.com/installation/index.html)

**Run tests:**
- In a terminal at the root of the project
    ```
    act -W .github/workflows/pythonapp.yml
    ```
