"""The serving side: storage, batch scoring, the worker and the HTTP API (final-spec components 11, 12, 14).

Nothing in this package imports the offline modules (evaluation, selection, experiment, exploration) or reads
private truth. It needs an artifact root and a PostgreSQL database, and nothing else.
"""
