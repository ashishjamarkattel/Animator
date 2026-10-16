#!/usr/bin/env bash
# One-time setup for a fresh Ubuntu VM (written for Oracle Cloud's Always Free Ampere A1):
# installs Docker and opens ports 80 and 443 in the VM's own firewall.
# Oracle also blocks them at the network level: add ingress rules for TCP 80 and 443
# (source 0.0.0.0/0) to the subnet's security list in the Oracle console.
set -euo pipefail

if ! command -v docker >/dev/null; then
    curl -fsSL https://get.docker.com | sudo sh
    sudo usermod -aG docker "$USER"
fi

# Oracle's Ubuntu images reject everything not explicitly allowed, before a final REJECT rule
for rule in "tcp --dport 80" "tcp --dport 443" "udp --dport 443"; do
    # shellcheck disable=SC2086
    sudo iptables -C INPUT -m state --state NEW -p $rule -j ACCEPT 2>/dev/null \
        || sudo iptables -I INPUT 6 -m state --state NEW -p $rule -j ACCEPT
done
if command -v netfilter-persistent >/dev/null; then
    sudo netfilter-persistent save
fi

echo "Done. Log out and back in so 'docker' works without sudo."
