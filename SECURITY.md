# Security policy

## Scope

r-offcall is a local-network meeting tool. It is not designed to be exposed to the public internet.

## Reporting a vulnerability

Please do **not** publish a security issue with a working exploit, credentials, or personal data. Contact the repository owner privately and include:

- a clear description of the issue;
- affected version or commit;
- minimal reproduction steps;
- impact and any suggested mitigation.

The owner should acknowledge the report, assess scope, and coordinate a fix before public disclosure.

## Deployment guidance

- Keep the host on a trusted, firewalled local network.
- Do not expose port `7800` to the public internet.
- Treat room passwords as a convenience control, not strong identity verification.
- Use operating-system updates and current browser engines on all participating devices.
