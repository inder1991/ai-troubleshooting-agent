Vagrant.configure("2") do |config|
  config.vm.box = "ubuntu/focal64"
  
  # Forward ports for Backend and Frontend
  config.vm.network "forwarded_port", guest: 8000, host: 8000 # Backend
  config.vm.network "forwarded_port", guest: 3000, host: 3000 # Frontend

  config.vm.provision "shell", inline: <<-SHELL
    sudo apt-get update
    sudo apt-get install -y python3-pip
    cd /vagrant
    pip3 install -r requirements.txt
    pip3 install ddtrace # Ensure ddtrace is available for the wrapper
  SHELL
end
