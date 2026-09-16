-- Synthetic fixture input only; SQLite-compatible DDL for integrity tests.
CREATE TABLE DimDate (
  Date TEXT NOT NULL PRIMARY KEY,
  Year INTEGER NOT NULL,
  Quarter INTEGER NOT NULL,
  MonthNumber INTEGER NOT NULL,
  MonthName TEXT NOT NULL,
  YearMonth TEXT NOT NULL
);
CREATE TABLE DimProduct (
  ProductId TEXT NOT NULL PRIMARY KEY,
  ProductName TEXT NOT NULL,
  ProductCategory TEXT NOT NULL,
  ProductSubcategory TEXT NOT NULL
);
CREATE TABLE DimRegion (
  RegionId TEXT NOT NULL PRIMARY KEY,
  RegionName TEXT NOT NULL,
  State TEXT NOT NULL,
  Country TEXT NOT NULL
);
CREATE TABLE DimBusinessArea (
  BusinessAreaId TEXT NOT NULL PRIMARY KEY,
  BusinessAreaName TEXT NOT NULL
);
CREATE TABLE DimCustomer (
  CustomerId TEXT NOT NULL PRIMARY KEY,
  Segment TEXT NOT NULL
);
CREATE TABLE FactSales (
  SaleId TEXT NOT NULL PRIMARY KEY,
  OrderId TEXT NOT NULL,
  SaleDate TEXT NOT NULL,
  ProductId TEXT NOT NULL,
  RegionId TEXT NOT NULL,
  BusinessAreaId TEXT NOT NULL,
  CustomerId TEXT NOT NULL,
  Quantity INTEGER NOT NULL,
  UnitPrice DECIMAL(12,2) NOT NULL,
  DiscountAmount DECIMAL(12,2) NOT NULL,
  SalesAmount DECIMAL(12,2) NOT NULL,
  CostAmount DECIMAL(12,2) NOT NULL,
  FOREIGN KEY (SaleDate) REFERENCES DimDate(Date),
  FOREIGN KEY (ProductId) REFERENCES DimProduct(ProductId),
  FOREIGN KEY (RegionId) REFERENCES DimRegion(RegionId),
  FOREIGN KEY (BusinessAreaId) REFERENCES DimBusinessArea(BusinessAreaId),
  FOREIGN KEY (CustomerId) REFERENCES DimCustomer(CustomerId)
);
