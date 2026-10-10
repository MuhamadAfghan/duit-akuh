"""Domain errors.

These are business-rule violations, not bugs. The API layer maps them to
4xx responses; the chat orchestrator turns them into a clarification
question rather than posting something wrong.
"""

from __future__ import annotations


class DomainError(Exception):
    """Base for every rule violation in the ledger."""

    code = "domain_error"


class UnbalancedTransaction(DomainError):
    """Entries did not sum to zero — the transaction would create or destroy money."""

    code = "unbalanced_transaction"


class AmbiguousAccount(DomainError):
    """A name matched more than one account.

    AC04 requires the user to choose; the system must never guess which
    account was meant.
    """

    code = "ambiguous_account"


class AccountNotFound(DomainError):
    code = "account_not_found"


class AccountArchived(DomainError):
    code = "account_archived"


class CrossUserAccess(DomainError):
    """An object was reached that belongs to another user.

    Should be impossible by construction; raised as a loud failure rather
    than returning empty, because silently returning nothing would hide a
    breach of the AC08 isolation gate.
    """

    code = "cross_user_access"


class InsufficientBalance(DomainError):
    """A balance would go negative without explicit confirmation (FR01)."""

    code = "insufficient_balance"


class AllocationExceedsBalance(DomainError):
    """Allocations on an account would exceed its positive balance (AC05)."""

    code = "allocation_exceeds_balance"


class InvalidTransaction(DomainError):
    code = "invalid_transaction"


class VersionConflict(DomainError):
    """Two devices edited the same version of an object (FR03)."""

    code = "version_conflict"
