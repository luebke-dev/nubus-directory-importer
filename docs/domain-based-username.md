# Domain-Based Username Feature

This feature automatically appends domain suffixes to usernames and organizes users into domain-specific organizational units (OUs) when synchronizing from Active Directory.

## Quick Start

Add these lines to the `source:` section of your existing config:

```yaml
source:
    enable_domain_based_username: true
    domain_based_username_attr: "username"       # attribute to append domain to
    domain_based_username_separator: "_"          # separator (default: "_")
```

Then run the importer as usual:

```bash
python -m univention.directory_importer config/your-config.yaml
```

## What Happens

### Before (without feature)

```
Source DN:  CN=John.Doe,OU=Users,DC=sub,DC=example,DC=com
Username:  john.doe
Target DN: uid=john.doe,ou=users,dc=...
```

### After (with feature)

```
Source DN:  CN=John.Doe,OU=Users,DC=sub,DC=example,DC=com
Username:  john.doe_sub.example.com
Target DN: uid=john.doe_sub.example.com,ou=sub.example.com,ou=users,dc=...
```

The connector:

1. **Extracts the domain** from DC components in the source DN (`DC=sub,DC=example,DC=com` → `sub.example.com`)
2. **Appends** it to the username (`john.doe` → `john.doe_sub.example.com`)
3. **Creates a domain sub-OU** automatically (`ou=sub.example.com`) and places the user there

## Configuration Reference

### `enable_domain_based_username`

| | |
|---|---|
| Type | `bool` |
| Default | `false` |
| Required | No |

Enables domain-based username transformation.

### `domain_based_username_attr`

| | |
|---|---|
| Type | `str` |
| Default | `"username"` |
| Required | No |

The target attribute to append the domain suffix to. Typically `"username"`.

### `domain_based_username_separator`

| | |
|---|---|
| Type | `str` |
| Default | `"_"` |
| Required | No |

The separator placed between the username and the domain part. Change to e.g. `"@"` if you prefer `user@domain.com` style.

## Example Scenarios

### Single Domain

```yaml
source:
    enable_domain_based_username: true
    user_base: "CN=Users,DC=example,DC=com"
```

| Source | Target Username | Target OU |
|--------|----------------|-----------|
| `CN=john,DC=example,DC=com` | `john_example.com` | `ou=example.com,ou=users,...` |

### Multiple Subdomains

```yaml
source:
    enable_domain_based_username: true
    user_base: "DC=example,DC=com"
```

| Source DN | Target Username | Target OU |
|-----------|----------------|-----------|
| `CN=User1,DC=sub,DC=example,DC=com` | `user1_sub.example.com` | `ou=sub.example.com,ou=users,...` |
| `CN=User2,DC=child,DC=sub,DC=example,DC=com` | `user2_sub.sub.example.com` | `ou=sub.sub.example.com,ou=users,...` |

### DN Without DC Components

If a DN has no DC components, the username is left unchanged and the user is placed in the base OU.

## Implementation Details

### Data Flow

```
Source LDAP Search
  ↓
source_search() yields (dn, attributes) tuples
  ↓
Standard Transformer (rename_attrs, sanitizer, etc.)
  ↓
DomainBasedUsernameTransformer (if enabled)
  - Receives source_dn as explicit parameter (not via record)
  - Extracts domain via ldap.dn.str2dn (robust against escaped chars)
  - Modifies username: username → username<separator>domain
  ↓
sync_entries()
  - Derives domain OU from source_dn directly
  - Creates domain OU once per domain (cached)
  - Places user under ou=<domain>,ou=<base_user_ou>,...
  ↓
UDM creates/updates user
```

### Source Code Components

| File | Component | Purpose |
|------|-----------|---------|
| `sanitize.py` | `extract_domain_from_dn()` | Extracts domain from DN using `ldap.dn.str2dn` |
| `trans.py` | `DomainBasedUsernameTransformer` | Transformer that appends domain to username |
| `connector.py` | `_ensure_domain_ou()` | Creates domain sub-OU (cached, at most once per domain) |
| `connector.py` | `_transform_entry()` | Applies standard + domain transformer |
| `config.py` | `SourceConfig` | Holds `enable_domain_based_username`, `domain_based_username_attr`, `domain_based_username_separator` |

### Design Decisions

- **No side-channel attributes**: The domain OU is derived directly from `source_dn` in the connector, not passed through the record via internal `_dn` or `_target_domain_ou` attributes.
- **Config is not mutated**: The connector keeps its own `_user_trans` / `_domain_username_trans` attributes instead of overwriting `config.src.user_trans`.
- **OU creation is cached**: A `set` tracks which domain OUs have already been created to avoid redundant HTTP calls.
- **DN parsing uses `ldap.dn.str2dn`**: Handles escaped commas, multi-valued RDNs, and other edge cases correctly.

## Troubleshooting

### Username is not modified

- Is `enable_domain_based_username: true` set?
- Does the source DN contain DC components?
- Is `domain_based_username_attr` set to the correct target attribute name?

### Sub-OU is not created

- Does the UDM user have permissions to create OUs?
- Is `skip_writes: false`?

### Enable debug logging

```bash
python -m univention.directory_importer --log-level DEBUG config/your-config.yaml
```

Look for:
```
INFO  Enabling domain-based username transformation (attribute: username, separator: _)
DEBUG Modified username from 'john.doe' to 'john.doe_sub.example.com' ...
DEBUG Using domain-based position 'ou=sub.example.com,ou=users,...' for entry ...
```

## Complete Config Example

See [config/ad-domain-config-with-domain-suffix.yaml.example](../config/ad-domain-config-with-domain-suffix.yaml.example) for a full working configuration.


## Behavior notes

- Pre-existing users are not moved: the domain sub-OU placement applies to
  newly created users only. Updates never change an entry's position (a
  changed position would be a move in the UDM REST API).
- Group names are not domain-suffixed. When several source domains share
  one target, make sure group names do not collide across domains.
