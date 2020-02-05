This describes the odoo connection specific syntax.
Other options are taken from standard pantable implementation, except for:
- `include`
- `include-encoding`
- `csv-kwargs`

Those are superseded by this odoo specific implementation.

Furthermore, only one content row is permitted which represents alternative
table headers to the odoo ones.

```odootable
---
url: odoo.host.com
database: odoo.host.com  # optional: takes same as url by default
port: 443  # optional: defaults to 80
model: res.partner
domain:
 - '&'
 -  # this is important
   - id
   - in
   - [1,2,3,4]
 -  # this is important
   - login
   - =
   - admin
fields:
 - name
 - email
 - phone
login: mylogin
password: xasderwerwer
---
First row,is overriding odoo headers,if not set odoo headers are used
```
