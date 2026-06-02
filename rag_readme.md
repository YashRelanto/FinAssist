# FinAssist Financial Advisor Engine

## Overview

FinAssist is a hybrid AI-powered Financial Advisor designed to provide users with:

* Personal transaction insights through NL2SQL
* Financial education and FAQs through RAG
* Goal-based financial planning
* Banking and investment guidance
* Product comparisons
* Market information retrieval
* Human-in-the-Loop (HITL) clarification for personalized recommendations

The system combines:

* Retrieval-Augmented Generation (RAG)
* Natural Language to SQL (NL2SQL)
* Human-in-the-Loop (HITL)
* Hybrid Knowledge Retrieval
* ChromaDB Vector Search
* Live Financial Data Retrieval
* Multi-Layer Security Guardrails

---

# High-Level Architecture

`                  ┌──────────────────────┐
                        │      User Query      │
                        └──────────┬───────────┘
                                   │
                                   ▼
                     ┌──────────────────────────┐
                     │   Input Guardrails       │
                     │ • Prompt Injection Check │
                     │ • Abuse Detection        │
                     │ • Query Validation       │
                     └──────────┬───────────────┘
                                │
                                ▼
                     ┌──────────────────────────┐
                     │      Intent Router       │
                     └──────────┬───────────────┘
                                │
          ┌─────────────────────┴─────────────────────┐
          │                                           │
          ▼                                           ▼

┌───────────────────┐                  ┌────────────────────────┐
│ Personal Finance  │                  │ Financial Advisor      │
│ Transaction       │                  │ Engine                 │
│ Queries           │                  └────────────┬───────────┘
└─────────┬─────────┘                               │
          │                                         ▼
          ▼                          ┌──────────────────────────┐
┌────────────────────┐               │ Query Type Detection     │
│      NL2SQL        │               └────────────┬─────────────┘
└─────────┬──────────┘                            │
          │                                       ▼
          ▼                        ┌────────────────────────────┐
┌────────────────────┐             │ Missing Information Check  │
│     Supabase       │             │ (Clarification Engine)     │
└─────────┬──────────┘             └────────────┬───────────────┘
          │                                     │
          ▼                                     ▼

┌────────────────────┐             ┌────────────────────────────┐
│ Transaction Answer │             │ Clarification Questions    │
└────────────────────┘             └────────────┬───────────────┘
                                                │
                                                ▼

                                  ┌────────────────────────────┐
                                  │ Hybrid Retrieval Layer     │
                                  └────────────┬───────────────┘
                                               │
                           ┌───────────────────┴──────────────────┐
                           │                                      │
                           ▼                                      ▼

              ┌───────────────────────┐         ┌───────────────────────┐
              │ ChromaDB Retrieval    │         │ Live Financial Search │
              │ (MMR Retrieval)       │         │ & Scraping            │
              └──────────┬────────────┘         └──────────┬────────────┘
                         │                                 │
                         └──────────────┬──────────────────┘
                                        │
                                        ▼

                          ┌────────────────────────────┐
                          │ Knowledge Aggregation      │
                          └────────────┬───────────────┘
                                       │
                                       ▼

                          ┌────────────────────────────┐
                          │ Financial Advisor LLM      │
                          └────────────┬───────────────┘
                                       │
                                       ▼

                          ┌────────────────────────────┐
                          │ Output Guardrails          │
                          │ • PII Protection           │
                          │ • Data Sanitization        │
                          │ • Response Validation      │
                          └────────────┬───────────────┘
                                       │
                                       ▼

                              ┌──────────────────┐
                              │ Final Response   │
                              └──────────────────┘

---

# System Components

## 1. Intent Router

The Intent Router determines whether a query should be handled by:

### NL2SQL Engine

Handles:

* Spending analysis
* Expense analysis
* Income analysis
* Transaction history
* Merchant analysis
* Category-wise spending
* Date-wise spending

Examples:

* How much did I spend on food last month?
* Show my Amazon transactions.
* How much salary did I receive in June?

### Financial Advisor Engine

Handles:

* Financial education
* Banking
* Investments
* Insurance
* Taxation
* Goal planning
* Product comparisons

---

# NL2SQL Engine

## Purpose

Convert user financial transaction queries into SQL queries dynamically.

The engine operates exclusively on the user's own transaction data.

---

## Flow

```text
User Query
     │
     ▼
Entity Extraction
     │
     ▼
Filter Detection
     │
     ▼
SQL Generation
     │
     ▼
Authorization Validation
     │
     ▼
Supabase Execution
     │
     ▼
Result Formatting
     │
     ▼
Answer
```

---

## Examples

### Category Analysis

User:

```text
How much did I spend on food?
```

Generated Query:

```sql
SELECT SUM(amount)
FROM transactions
WHERE category = 'Food'
AND user_id = ?
```

---

### Merchant Analysis

User:

```text
How much did I spend on Amazon?
```

Generated Query:

```sql
SELECT SUM(amount)
FROM transactions
WHERE merchant_name = 'Amazon'
AND user_id = ?
```

---

### Date Analysis

User:

```text
How much did I spend on January 5?
```

Generated Query:

```sql
SELECT SUM(amount)
FROM transactions
WHERE transaction_date = '2025-01-05'
AND user_id = ?
```

---

# Financial Advisor Engine

The advisor handles all non-personal-data financial questions.

---

# Query Categories

The advisor dynamically classifies queries into:

* Educational
* Market Information
* Product Comparison
* Goal Planning
* Investment Planning
* Banking Products
* Insurance
* Taxation
* Retirement Planning

---

# Human-in-the-Loop (HITL)

## Purpose

Prevent incorrect recommendations caused by missing information.

The advisor should never make assumptions.

---

## Example

User:

```text
I want to buy a bike next year.
```

Missing Information:

* Bike model
* Budget
* Timeline
* Existing savings

Advisor Response:

```text
To help you create a plan:

1. Which bike are you planning to buy?
2. What's your estimated budget?
3. How much have you already saved?
4. When do you plan to purchase it?
```

Only after collecting the missing information should recommendations be generated.

---

# Slot Filling Engine

Each advisory category defines required information.

## Goal Planning

Required:

* Goal
* Budget
* Timeline
* Existing savings

---

## Investment Planning

Required:

* Risk profile
* Investment amount
* Investment horizon
* Financial objective

---

## Banking Products

Required:

* Amount
* Tenure
* Existing banking relationship
* Senior citizen status

---

## Insurance

Required:

* Age
* Dependents
* Coverage objective

---

# Hybrid Retrieval Strategy

The advisor does not rely solely on ChromaDB.

It combines:

1. Cached Knowledge
2. Live Financial Retrieval

---

## Flow

```text
User Query
      │
      ▼
Chroma Search
      │
      ▼
Confidence Check
      │
 ┌────┴────┐
 │         │
High      Low
 │         │
 ▼         ▼

Answer   Live Retrieval
              │
              ▼

      Store New Knowledge
              │
              ▼

           Answer
```

---

# ChromaDB Knowledge Layer

## Purpose

Serve as a high-speed knowledge cache.

Contains:

* Banking information
* Investment information
* Financial education
* Financial tips
* Historical retrieval results

---

## Retrieval Method

Maximum Marginal Relevance (MMR)

Benefits:

* Diverse context retrieval
* Reduced duplicate chunks
* Better answer quality
* Improved context coverage

---

# Live Financial Retrieval

Triggered when:

* Retrieval confidence is low
* Information is stale
* Information is missing

Examples:

* New FD rates
* RBI announcements
* Market updates
* Recently launched products

---

# Knowledge Refresh Strategy

## Scheduled Updates

### Every 6–12 Hours

* FD Rates
* RD Rates
* Savings Rates
* Loan Rates
* Credit Card Information

### Weekly

* Financial Tips
* Educational Articles
* Market Commentary

### Monthly

* Government Schemes
* NPS Updates
* Tax Updates
* Policy Changes

---

## Dynamic Updates

If a user asks a question unavailable in ChromaDB:

```text
Live Retrieval
      │
      ▼
Answer Generation
      │
      ▼
Store in ChromaDB
```

This continuously improves system coverage.

---

# Source Priority Framework

The advisor ranks sources based on trust.

## Tier 1

Highest Trust

* RBI
* SEBI
* Income Tax Department
* NPS Trust
* Government Portals

## Tier 2

High Trust

* Groww
* ET Money
* MoneyControl
* Value Research

## Tier 3

Moderate Trust

* BankBazaar
* PolicyBazaar
* Financial Blogs

---

# Security Architecture

The system uses four protection layers.

## Layer 1 — Input Guardrails

Protects against:

* Prompt Injection
* Abuse
* Excessive Input
* Malicious Requests

---

## Layer 2 — Authorization Guard

Ensures:

* User can only access their own data
* SQL queries contain mandatory user filtering

---

## Layer 3 — PII Protection

Masks:

* PAN
* Aadhaar
* Phone Numbers
* Email Addresses
* Account Numbers
* UPI IDs

---

## Layer 4 — Output Guardrails

Prevents:

* Secret leakage
* SQL leakage
* PII exposure

---

# Response Standards

Every advisor response should follow:

```text
Short Answer

Key Insights
- Point 1
- Point 2
- Point 3

Recommendation
- Suggested action

Next Step
- Clear user action
```

---

# Design Principles

The system should:

✓ Ask before assuming

✓ Personalize recommendations

✓ Retrieve trusted information

✓ Separate personal data from advisory data

✓ Explain reasoning clearly

✓ Maintain financial safety

✓ Continuously improve knowledge coverage

✓ Use HITL only when necessary

✓ Keep responses concise and structured

✓ Prioritize user understanding over complexity

---

# Future Enhancements

* Portfolio Analysis Engine
* Budget Planning Engine
* Goal Tracking Engine
* Financial Health Score
* Personalized Recommendation Engine
* Real-Time Market Monitoring
* Automated Knowledge Refresh Pipelines
* User Preference Memory
* Recommendation Explainability Layer

---

# Summary

FinAssist combines:

* NL2SQL for personal financial analytics
* Hybrid RAG for financial knowledge
* HITL for personalized planning
* ChromaDB for fast retrieval
* Live Retrieval for freshness
* MMR for better context diversity
* Multi-layer security for safe financial assistance

This architecture enables scalable, accurate, explainable, and user-centric financial advisory experiences while maintaining strong security, personalization, and data isolation guarantees.
