-- Runs once, when the PostgreSQL data directory is created: Keycloak keeps its tables in its own database on the same
-- server (deploy/aws/compose.vm.yml). ARAI's own database "arai" is created by the image from POSTGRES_DB.
CREATE DATABASE keycloak OWNER arai;
