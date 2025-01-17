# Luma Handler

Luma handler for MindsDB provides interfaces to connect to LUMA Events via APIs and pull event data into MindsDB.

---

## Table of Contents

- [Luma Handler](#luma-handler)
  - [Table of Contents](#table-of-contents)
  - [About LUMA](#about-luma)
  - [LUMA Handler Implementation](#luma-handler-implementation)
  - [LUMA Handler Initialization](#luma-handler-initialization)
  - [Implemented Features](#implemented-features)
  - [TODO Features](#todo-features)
  - [Example Usage](#example-usage)

---

## About LUMA

From beautiful event pages to effortless invites and ticketing, Luma is all you need to host a memorable event.

## LUMA Handler Implementation

This handler was implemented using the `requests` library that makes http calls to https://docs.lu.ma/reference/getting-started-with-your-api

## LUMA Handler Initialization

The Luma handler is initialized with the following parameters:

- `api_key`: API Key

Read about creating an API key [here](https://docs.lu.ma/reference/getting-started-with-your-api).

## Implemented Features

- [x] LUMA List Events
- [x] LUMA Get an event

## TODO Features

- [ ] Get Event Guest List - This needs actual guests to be enrolled
- [ ] Update Event Guest Status - This needs actual guests to be enrolled
- [ ] LUMA Create an event - Need to implement it in handler and tables

## Example Usage

The first step is to create a database with the new `luma` engine. 

~~~~sql
CREATE DATABASE mindsdb_luma
WITH ENGINE = 'luma',
PARAMETERS = {
  "api_key": "api_key"
};
~~~~

Use the established connection to query your database:

~~~~sql
SELECT * FROM mindsdb_luma.events;
~~~~

~~~~sql
SELECT * FROM mindsdb_luma.events where event_id="evt-HQ36IFDwncocuGy";
~~~~

