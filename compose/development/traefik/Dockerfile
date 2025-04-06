FROM docker.io/traefik:3.3.5

# Ensure the /etc/traefik directory exists
RUN mkdir -p /etc/traefik

# Copy the Traefik configuration file into the directory
COPY ./compose/development/traefik/traefik.yml /etc/traefik/traefik.yml
