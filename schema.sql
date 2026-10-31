CREATE TABLE IF NOT EXISTS users (
  id INT AUTO_INCREMENT PRIMARY KEY,
  username VARCHAR(50) UNIQUE NOT NULL,
  full_name VARCHAR(100) NOT NULL,
  password_hash VARCHAR(255) NOT NULL,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS rides (
  id INT AUTO_INCREMENT PRIMARY KEY,
  driver_id INT NOT NULL,
  origin VARCHAR(100) NOT NULL,
  destination VARCHAR(100) NOT NULL,
  depart_at DATETIME NOT NULL,
  seats INT NOT NULL,
  price INT NOT NULL DEFAULT 0,
  status ENUM('open','cancelled') NOT NULL DEFAULT 'open',
  FOREIGN KEY (driver_id) REFERENCES users(id)
);
CREATE TABLE IF NOT EXISTS bookings (
  id INT AUTO_INCREMENT PRIMARY KEY,
  ride_id INT NOT NULL,
  rider_id INT NOT NULL,
  status ENUM('pending','approved','rejected','cancelled') NOT NULL DEFAULT 'pending',
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (ride_id) REFERENCES rides(id),
  FOREIGN KEY (rider_id) REFERENCES users(id)
);
