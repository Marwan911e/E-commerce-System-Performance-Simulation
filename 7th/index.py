import simpy
import statistics
import random

class EcommerceSystem:
    def __init__(self, env, num_servers, processing_time=0.25, max_queue_size=20, timeout=5.0):
        self.env = env
        self.server = simpy.Resource(env, num_servers)
        self.processing_time = processing_time  # 250ms = 0.25s
        self.response_times = []
        self.queue_lengths = []
        self.dropped_requests = 0
        self.total_requests = 0
        self.server_busy_time = 0
        self.last_busy_check = 0
        self.utilization_samples = []
        self.max_queue_size = max_queue_size  # Maximum queue size before dropping requests
        self.timeout = timeout  # Maximum wait time before timeout (in seconds)
    
    def handle_request(self, user_id):
        self.total_requests += 1
        arrival_time = self.env.now
        
        # Check if queue is full and drop request if needed
        if len(self.server.queue) >= self.max_queue_size:
            self.dropped_requests += 1
            return
        
        # Record queue length
        self.queue_lengths.append(len(self.server.queue))
        
        # Request a server with timeout
        with self.server.request() as request:
            # Try to get a server within timeout period
            results = yield self.env.timeout(self.timeout) | request
            
            # If timeout occurred before getting a server
            if request not in results:
                self.dropped_requests += 1
                return
            
            # Track server busy time for utilization calculation
            request_start = self.env.now
            
            # Process the request
            yield self.env.timeout(self.processing_time)
            
            # Record response time
            response_time = self.env.now - arrival_time
            self.response_times.append(response_time)
            
            # Update server busy time
            self.server_busy_time += self.env.now - request_start

    def sample_utilization(self):
        """Take a sample of current server utilization"""
        if self.server.capacity > 0:
            current_utilization = len(self.server.users) / self.server.capacity
            self.utilization_samples.append(current_utilization)
            self.last_busy_check = self.env.now

def run_simulation(env, system, num_users, arrival_rate):
    """Run the e-commerce simulation for a specific user count"""
    # Generate user arrivals
    for i in range(num_users):
        env.process(system.handle_request(i))
        yield env.timeout(random.expovariate(arrival_rate))

def utilization_monitor(env, system):
    """Process to sample utilization at regular intervals"""
    while True:
        system.sample_utilization()
        yield env.timeout(0.1)  # Sample every 0.1 time units

def static_simulation(num_servers, num_users, duration=60, max_queue_size=20, timeout=5.0):
    """Run simulation with static number of servers"""
    env = simpy.Environment()
    system = EcommerceSystem(env, num_servers=num_servers, max_queue_size=max_queue_size, timeout=timeout)
    
    # Start utilization monitoring process
    env.process(utilization_monitor(env, system))
    
    # Start user arrivals process
    env.process(run_simulation(env, system, num_users, arrival_rate=num_users/duration))
    
    # Run simulation
    env.run(until=duration)
    
    # Calculate statistics
    avg_response_time = statistics.mean(system.response_times) if system.response_times else 0
    avg_queue_length = statistics.mean(system.queue_lengths) if system.queue_lengths else 0
    avg_utilization = statistics.mean(system.utilization_samples) if system.utilization_samples else 0
    dropped_rate = (system.dropped_requests / system.total_requests * 100) if system.total_requests > 0 else 0
    
    return {
        'avg_response_time': avg_response_time * 1000,  # Convert to ms
        'avg_queue_length': avg_queue_length,
        'num_requests': len(system.response_times),
        'total_requests': system.total_requests,
        'dropped_requests': system.dropped_requests,
        'dropped_rate': dropped_rate,  # Percentage of dropped requests
        'avg_utilization': avg_utilization * 100  # Convert to percentage
    }

def dynamic_simulation(min_servers, max_servers, num_users, duration=60, max_queue_size=20, timeout=5.0):
    """Run simulation with dynamic scaling of servers"""
    env = simpy.Environment()
    system = EcommerceSystem(env, num_servers=min_servers, max_queue_size=max_queue_size, timeout=timeout)
    servers_added = []
    current_servers = min_servers
    
    # Process to monitor and scale servers
    def auto_scale():
        nonlocal current_servers
        while True:
            # Check if we need to scale up (if queue is getting long)
            if len(system.server.queue) > 5 and current_servers < max_servers:
                current_servers += 1
                old_server = system.server
                system.server = simpy.Resource(env, current_servers)
                # Transfer any users from old server to new one
                system.server.users = old_server.users
                system.server.queue = old_server.queue
                servers_added.append((env.now, current_servers))
                print(f"Time {env.now:.2f}: Scaled up to {current_servers} servers")
            
            # Check if we need to scale down
            elif len(system.server.queue) == 0 and len(system.server.users) / current_servers < 0.5 and current_servers > min_servers:
                current_servers -= 1
                old_server = system.server
                system.server = simpy.Resource(env, current_servers)
                # Transfer any users from old server to new one
                system.server.users = old_server.users
                system.server.queue = old_server.queue
                servers_added.append((env.now, current_servers))
                print(f"Time {env.now:.2f}: Scaled down to {current_servers} servers")
            
            yield env.timeout(5)  # Check every 5 time units
    
    # Start utilization monitoring process
    env.process(utilization_monitor(env, system))
    
    # Start autoscaling and user arrivals
    env.process(auto_scale())
    env.process(run_simulation(env, system, num_users, arrival_rate=num_users/duration))
    
    # Run simulation
    env.run(until=duration)
    
    # Calculate statistics
    avg_response_time = statistics.mean(system.response_times) if system.response_times else 0
    avg_queue_length = statistics.mean(system.queue_lengths) if system.queue_lengths else 0
    avg_utilization = statistics.mean(system.utilization_samples) if system.utilization_samples else 0
    dropped_rate = (system.dropped_requests / system.total_requests * 100) if system.total_requests > 0 else 0
    
    return {
        'avg_response_time': avg_response_time * 1000,  # Convert to ms
        'avg_queue_length': avg_queue_length,
        'num_requests': len(system.response_times),
        'total_requests': system.total_requests,
        'dropped_requests': system.dropped_requests,
        'dropped_rate': dropped_rate,  # Percentage of dropped requests
        'servers_added': servers_added,
        'final_servers': current_servers,
        'avg_utilization': avg_utilization * 100  # Convert to percentage
    }

def print_results(title, results):
    print(f"\n=== {title} ===")
    print(f"Average Response Time: {results['avg_response_time']:.2f} ms")
    print(f"Average Queue Length: {results['avg_queue_length']:.2f}")
    print(f"Average Server Utilization: {results['avg_utilization']:.2f}%")
    print(f"Total Requests: {results['total_requests']}")
    print(f"Successfully Processed: {results['num_requests']}")
    print(f"Dropped Requests: {results['dropped_requests']} ({results['dropped_rate']:.2f}%)")
    if 'final_servers' in results:
        print(f"Final Server Count: {results['final_servers']}")

def main():
    print("=== E-Commerce System Performance Simulation ===")
    print("This simulation analyzes system performance for an e-commerce platform.")
    
    while True:
        print("\nChoose a simulation option:")
        print("1. Response Time Under Different Concurrent Users")
        print("2. Server Requirements for 600ms Response Time")
        print("3. Simulation of Static and Dynamic Scaling")
        print("4. Exit")
        
        choice = input("\nEnter your choice (1-4): ")
        
        if choice == "1":
            print("\n=== Response Time vs. Concurrent Users ===")
            print("| Users | Servers | Resp Time (ms) | Queue Length | Utilization (%) | Dropped (%) |")
            print("|-------|---------|----------------|--------------|-----------------|-------------|")
            
            for users in [100, 300, 500, 700, 900]:
                results = static_simulation(num_servers=1, num_users=users)
                print(f"| {users:5d} | {1:7d} | {results['avg_response_time']:14.2f} | {results['avg_queue_length']:12.2f} | {results['avg_utilization']:15.2f} | {results['dropped_rate']:11.2f} |")
        
        elif choice == "2":
            print("\n=== Finding Optimal Server Count (700 users) ===")
            print("| Servers | Resp Time (ms) | Queue Length | Utilization (%) | Dropped (%) |")
            print("|---------|----------------|--------------|-----------------|-------------|")
            
            optimal_servers = 0
            for servers in range(1, 11):
                results = static_simulation(num_servers=servers, num_users=700)
                print(f"| {servers:7d} | {results['avg_response_time']:14.2f} | {results['avg_queue_length']:12.2f} | {results['avg_utilization']:15.2f} | {results['dropped_rate']:11.2f} |")
                
                if results['avg_response_time'] < 600 and optimal_servers == 0:
                    optimal_servers = servers
            
            print(f"\nOptimal server count: {optimal_servers} servers needed for <600ms response time")
        
        elif choice == "3":
            scaling_type = input("Choose scaling type (static/dynamic): ").lower()
            
            if scaling_type == "static":
                servers = int(input("Enter number of servers: "))
                users = int(input("Enter number of concurrent users: "))
                
                results = static_simulation(num_servers=servers, num_users=users)
                print_results(f"Static Simulation ({servers} servers, {users} users)", results)
                
            elif scaling_type == "dynamic":
                min_servers = int(input("Enter minimum servers: "))
                max_servers = int(input("Enter maximum servers: "))
                users = int(input("Enter number of concurrent users: "))
                
                results = dynamic_simulation(min_servers=min_servers, max_servers=max_servers, num_users=users)
                print_results(f"Dynamic Simulation ({min_servers}-{max_servers} servers, {users} users)", results)
                
                if results['servers_added']:
                    print("\nServer Scaling Events:")
                    for time, servers in results['servers_added']:
                        print(f"Time {time:.1f}: Changed to {servers} servers")
                        
                    # Add utilization report at scaling events
                    print("\nUtilization led to these scaling decisions.")
            else:
                print("Invalid scaling type selected.")
        
        elif choice == "4":
            print("Exiting simulation. Goodbye!")
            break
        
        else:
            print("Invalid choice. Please select 1-4.")

if __name__ == "__main__":
    # Seed for reproducibility
    random.seed(42)
    main()