# Spec change for v1.4: GET /api/v1/admin/users

Approved by the System Architect. Paste into section 5 (Endpoint contracts), directly before
`PATCH /api/v1/admin/users/{id}/role`, and update the version to v1.4.

---

**GET /api/v1/admin/users**

Access: ADMIN | List users

Request / query example:

```
GET /admin/users?search=student&role=STUDENT&page=1&page_size=20
```

Success response:

```json
{
  "items": [
    {
      "id": 12,
      "full_name": "Example Student",
      "email": "student@example.edu",
      "role": "STUDENT",
      "is_active": true,
      "created_at": "2026-11-19T12:00:00+03:00"
    }
  ],
  "page": 1,
  "page_size": 20,
  "total": 1
}
```

Rules: 200 OK; ADMIN only. Lists active and inactive users, ordered by full_name. Optional
filters: `search` (case-insensitive match on full_name or email) and `role`. Standard pagination.
Never returns password hashes or session data. Used by the admin dashboard to choose a user for
`PATCH /admin/users/{id}/role`.

---

Also add to section 10 (acceptance criteria):

| Test | Expected result |
| --- | --- |
| Non-ADMIN calls user list | 403 |
| User list response | No password hash or session data |
