#!/bin/bash

################################################################################
# Docker & Docker Compose Installation Script (Updated Version)
# Purpose: Install Docker, Docker Compose, and fix all permission issues
# Usage: sudo bash install-docker.sh
# Version: 2.0
################################################################################

set -e  # Exit on error

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Print functions
print_header() {
    echo ""
    echo -e "${CYAN}================================${NC}"
    echo -e "${CYAN}$1${NC}"
    echo -e "${CYAN}================================${NC}"
    echo ""
}

print_step() {
    echo -e "${BLUE}[$1] $2${NC}"
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

print_info() {
    echo -e "${CYAN}ℹ $1${NC}"
}

# Check if running as root
check_root() {
    if [ "$EUID" -ne 0 ]; then 
        print_error "Please run this script as root or with sudo"
        echo "Usage: sudo bash install-docker.sh"
        exit 1
    fi
}

# Get actual user
get_user() {
    ACTUAL_USER="${SUDO_USER:-$USER}"
    if [ "$ACTUAL_USER" = "root" ]; then
        print_warning "Running as root user. Docker will be configured for root."
        print_warning "It's recommended to run this script with sudo from a regular user."
        read -p "Continue anyway? (y/n): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            exit 1
        fi
    fi
}

# Display system info
show_system_info() {
    print_header "System Information"
    echo "OS: $(lsb_release -d | cut -f2)"
    echo "Kernel: $(uname -r)"
    echo "User: $ACTUAL_USER"
    echo "Architecture: $(uname -m)"
}

# Update system
update_system() {
    print_step "1/9" "Updating package lists..."
    apt-get update -y > /dev/null 2>&1
    print_success "Package lists updated"
}

# Check if Docker is already installed
check_docker_installed() {
    if command -v docker &> /dev/null; then
        DOCKER_VERSION=$(docker --version)
        print_warning "Docker is already installed: $DOCKER_VERSION"
        read -p "Reinstall/Update? (y/n): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            print_info "Skipping Docker installation"
            return 1
        fi
    fi
    return 0
}

# Install Docker
install_docker() {
    print_step "2/9" "Installing Docker..."
    
    # Install dependencies
    apt-get install -y \
        apt-transport-https \
        ca-certificates \
        curl \
        gnupg \
        lsb-release > /dev/null 2>&1
    
    # Install Docker
    apt-get install -y docker.io > /dev/null 2>&1
    
    print_success "Docker installed"
}

# Start Docker service
start_docker_service() {
    print_step "3/9" "Configuring Docker service..."
    
    systemctl start docker
    systemctl enable docker > /dev/null 2>&1
    
    # Wait for Docker to be ready
    sleep 2
    
    if systemctl is-active --quiet docker; then
        print_success "Docker service is running"
    else
        print_error "Docker service failed to start"
        exit 1
    fi
}

# Setup Docker group
setup_docker_group() {
    print_step "4/9" "Setting up Docker group..."
    
    # Create docker group if it doesn't exist
    if ! getent group docker > /dev/null 2>&1; then
        groupadd docker
        print_success "Docker group created"
    else
        print_info "Docker group already exists"
    fi
    
    # Add user to docker group
    if id -nG "$ACTUAL_USER" | grep -qw docker; then
        print_info "User $ACTUAL_USER is already in docker group"
    else
        usermod -aG docker "$ACTUAL_USER"
        print_success "User $ACTUAL_USER added to docker group"
    fi
}

# Fix Docker socket permissions
fix_socket_permissions() {
    print_step "5/9" "Setting Docker socket permissions..."
    
    if [ -S /var/run/docker.sock ]; then
        chown root:docker /var/run/docker.sock
        chmod 660 /var/run/docker.sock
        print_success "Docker socket permissions set (660, root:docker)"
    else
        print_warning "Docker socket not found (this is unusual)"
    fi
}

# Install Docker Compose
install_docker_compose() {
    print_step "6/9" "Installing Docker Compose..."
    
    # Try plugin first
    if apt-cache show docker-compose-plugin &> /dev/null; then
        apt-get install -y docker-compose-plugin > /dev/null 2>&1
        print_success "Docker Compose plugin installed"
    else
        print_warning "Docker Compose plugin not available in repository"
    fi
    
    # Install standalone version
    print_info "Installing standalone Docker Compose..."
    
    # Get latest version
    COMPOSE_VERSION=$(curl -s https://api.github.com/repos/docker/compose/releases/latest | grep 'tag_name' | cut -d '"' -f 4 2>/dev/null)
    
    # Fallback to known good version if API fails
    if [ -z "$COMPOSE_VERSION" ]; then
        COMPOSE_VERSION="v2.24.5"
        print_warning "Using fallback version: $COMPOSE_VERSION"
    fi
    
    # Download and install
    curl -sL "https://github.com/docker/compose/releases/download/${COMPOSE_VERSION}/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
    chmod +x /usr/local/bin/docker-compose
    
    # Verify installation
    if /usr/local/bin/docker-compose --version > /dev/null 2>&1; then
        print_success "Docker Compose standalone installed: $COMPOSE_VERSION"
    else
        print_error "Docker Compose installation failed"
    fi
}

# Test Docker installation
test_docker() {
    print_step "7/9" "Testing Docker installation..."
    
    # Test as root first
    if docker ps > /dev/null 2>&1; then
        print_success "Docker is working (as root)"
    else
        print_error "Docker test failed"
        return 1
    fi
    
    # Check if socket has correct permissions
    SOCKET_PERMS=$(stat -c %a /var/run/docker.sock 2>/dev/null || echo "000")
    if [ "$SOCKET_PERMS" = "660" ]; then
        print_success "Docker socket has correct permissions (660)"
    else
        print_warning "Docker socket permissions: $SOCKET_PERMS (expected: 660)"
    fi
}

# Create helper scripts
create_helper_scripts() {
    print_step "8/9" "Creating helper scripts..."
    
    # Create docker-test script
    cat > /usr/local/bin/docker-test <<'EOF'
#!/bin/bash
echo "Testing Docker installation..."
echo ""
echo "1. Testing docker command:"
docker --version
echo ""
echo "2. Testing docker ps:"
docker ps
echo ""
echo "3. Testing with hello-world:"
docker run --rm hello-world
echo ""
echo "4. Testing Docker Compose:"
docker-compose --version
echo ""
echo "All tests passed! Docker is working correctly."
EOF
    chmod +x /usr/local/bin/docker-test
    
    print_success "Helper scripts created"
    print_info "You can run 'docker-test' to verify installation"
}

# Display versions
show_versions() {
    print_step "9/9" "Verifying installations..."
    echo ""
    
    if command -v docker &> /dev/null; then
        echo -e "${GREEN}Docker:${NC} $(docker --version)"
    fi
    
    if command -v docker-compose &> /dev/null; then
        echo -e "${GREEN}Docker Compose (standalone):${NC} $(docker-compose --version)"
    fi
    
    if docker compose version &> /dev/null; then
        echo -e "${GREEN}Docker Compose (plugin):${NC} $(docker compose version)"
    fi
    
    echo ""
}

# Display completion message
show_completion() {
    print_header "Installation Complete!"
    
    echo -e "${GREEN}✓ Docker installed and configured${NC}"
    echo -e "${GREEN}✓ Docker Compose installed${NC}"
    echo -e "${GREEN}✓ User $ACTUAL_USER added to docker group${NC}"
    echo -e "${GREEN}✓ Permissions configured${NC}"
    echo ""
    
    print_header "CRITICAL: Apply Group Changes"
    
    echo -e "${YELLOW}Your user has been added to the docker group, but you need to apply this change.${NC}"
    echo ""
    echo -e "${GREEN}Choose ONE of these options:${NC}"
    echo ""
    echo -e "${CYAN}Option 1 - Quick (Recommended):${NC}"
    echo -e "   Run this command now:"
    echo -e "   ${BLUE}newgrp docker${NC}"
    echo ""
    echo -e "${CYAN}Option 2 - Permanent:${NC}"
    echo -e "   Logout and login again:"
    echo -e "   ${BLUE}exit${NC}"
    echo -e "   Then SSH back into the server"
    echo ""
    
    print_header "Test Your Installation"
    
    echo -e "After applying group changes, test with:"
    echo ""
    echo -e "   ${BLUE}docker ps${NC}                  # Should work without sudo"
    echo -e "   ${BLUE}docker run hello-world${NC}     # Test with a container"
    echo -e "   ${BLUE}docker-compose --version${NC}   # Check compose"
    echo -e "   ${BLUE}docker-test${NC}                # Run comprehensive test"
    echo ""
    
    print_header "Current Status"
    
    echo "Docker service: $(systemctl is-active docker)"
    echo "Docker group members: $(getent group docker | cut -d: -f4)"
    echo "Socket permissions: $(ls -l /var/run/docker.sock 2>/dev/null | awk '{print $1, $3, $4}')"
    echo ""
    
    print_header "Quick Reference"
    
    echo -e "${CYAN}Useful Commands:${NC}"
    echo "  docker ps                    # List running containers"
    echo "  docker ps -a                 # List all containers"
    echo "  docker images                # List images"
    echo "  docker-compose up -d         # Start services"
    echo "  docker-compose down          # Stop services"
    echo "  docker system prune          # Clean up"
    echo ""
    
    print_warning "Remember: Run 'newgrp docker' or logout/login to use Docker without sudo!"
    echo ""
}

# Main execution
main() {
    print_header "Docker Installation Script v2.0"
    
    check_root
    get_user
    show_system_info
    
    echo ""
    read -p "Continue with installation? (y/n): " -n 1 -r
    echo ""
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        print_info "Installation cancelled"
        exit 0
    fi
    
    echo ""
    update_system
    
    if check_docker_installed; then
        install_docker
    fi
    
    start_docker_service
    setup_docker_group
    fix_socket_permissions
    install_docker_compose
    test_docker
    create_helper_scripts
    show_versions
    
    echo ""
    show_completion
}

# Run main function
main
