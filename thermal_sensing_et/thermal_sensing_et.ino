/*
  Output the temperature readings to all pixels to be read by a Processing visualizer
  By: Nathan Seidle
  SparkFun Electronics
  Date: May 22nd, 2018
  License: MIT. See license file for more information but you can
  basically do whatever you want with this code.

  Feel like supporting open source hardware?
  Buy a board from SparkFun! https://www.sparkfun.com/products/14769

  This example outputs 768 temperature values as fast as possible. Use this example
  in conjunction with our Processing visualizer.

  This example will work with a Teensy 3.1 and above. The MLX90640 requires some
  hefty calculations and larger arrays. You will need a microcontroller with 20,000
  bytes or more of RAM.

  This relies on the driver written by Melexis and can be found at:
  https://github.com/melexis/mlx90640-library

  Hardware Connections:
  Connect the SparkFun Qwiic Breadboard Jumper (https://www.sparkfun.com/products/14425)
  to the Qwiic board
  Connect the male pins to the Teensy. The pinouts can be found here: https://www.pjrc.com/teensy/pinout.html
  Open the serial monitor at 115200 baud to see the output
*/

#include <Wire.h>
#include <SPI.h>
#include <SD.h>
#include <DHT.h>

#include "MLX90640_API.h"
#include "MLX90640_I2C_Driver.h"

const byte MLX90640_address = 0x33; //Default 7-bit unshifted address of the MLX90640

#define TA_SHIFT 8 //Default shift for MLX90640 in open air

// ---- SD card (VSPI default pins: SCK=18, MISO=19, MOSI=23) ----
#define SD_CS_PIN 5
const char *LOG_FILENAME = "/thermal_log.bin";

// ---- Fixed-point encoding ----
// Store each temperature as (float * TEMP_SCALE) rounded to the nearest int16_t.
// TEMP_SCALE=100 gives 0.01C resolution (rounding error <= 0.005C), well inside
// your +-0.1C budget, across the full -327.67C to 327.67C range of an int16_t.
#define TEMP_SCALE 100
#define FILE_MAGIC 0x54484D31UL //"THM1" - lets a decoder confirm the format/scale

//Binary layout: one 8-byte file header, then one FrameRecord per sample.
typedef struct __attribute__((packed)) {
  uint32_t magic;      //FILE_MAGIC
  uint16_t numPixels;  //768
  uint16_t scale;      //TEMP_SCALE
} FileHeader;

typedef struct __attribute__((packed)) {
  uint32_t timestamp_ms;
  int16_t pixels[768];
} FrameRecord;

// ---- DHT11 Temperature/Humidity ----
#define DHT_PIN 4
#define DHT_TYPE DHT11
DHT dht(DHT_PIN, DHT_TYPE);

const char *DHT_LOG_FILENAME = "/dht_log.csv";
const unsigned long DHT_READ_INTERVAL_MS = 2000; //DHT11 can't be read faster than ~1Hz reliably
unsigned long lastDhtReadMs = 0;

float mlx90640To[768];
paramsMLX90640 mlx90640;

bool sdReady = false;
unsigned long lastSdAttemptMs = 0;
const unsigned long SD_RETRY_INTERVAL_MS = 2000; //don't hammer the SPI bus every loop while the card is out

void setup()
{
  Wire.begin();
  Wire.setClock(400000); //Increase I2C clock speed to 400kHz

  Serial.begin(115200); //Fast serial as possible
  
  while (!Serial); //Wait for user to open terminal
  //Serial.println("MLX90640 IR Array Example");

  if (isConnected() == false)
  {
    Serial.println("MLX90640 not detected at default I2C address. Please check wiring. Freezing.");
    while (1);
  }

  //Get device parameters - We only have to do this once
  int status;
  uint16_t eeMLX90640[832];
  status = MLX90640_DumpEE(MLX90640_address, eeMLX90640);
  if (status != 0)
    Serial.println("Failed to load system parameters");

  status = MLX90640_ExtractParameters(eeMLX90640, &mlx90640);
  if (status != 0)
    Serial.println("Parameter extraction failed");

  //Once params are extracted, we can release eeMLX90640 array

  //MLX90640_SetRefreshRate(MLX90640_address, 0x02); //Set rate to 2Hz
  MLX90640_SetRefreshRate(MLX90640_address, 0x03); //Set rate to 4Hz
  //MLX90640_SetRefreshRate(MLX90640_address, 0x07); //Set rate to 64Hz

  //---- Initialize SD card (non-fatal: keep sampling even if no card yet) ----
  sdReady = initSD();
  if (sdReady)
    Serial.println("SD card initialized.");
  else
    Serial.println("No SD card detected. Will keep sampling and retry periodically; insert a card any time.");

  //---- Initialize DHT11 ----
  dht.begin();
}

void loop()
{
  long startTime = millis();
  for (byte x = 0 ; x < 2 ; x++)
  {
    uint16_t mlx90640Frame[834];
    int status = MLX90640_GetFrameData(MLX90640_address, mlx90640Frame);

    float vdd = MLX90640_GetVdd(mlx90640Frame, &mlx90640);
    float Ta = MLX90640_GetTa(mlx90640Frame, &mlx90640);

    float tr = Ta - TA_SHIFT; //Reflected temperature based on the sensor ambient temperature
    float emissivity = 0.95;

    MLX90640_CalculateTo(mlx90640Frame, &mlx90640, emissivity, tr, mlx90640To);
  }
  long stopTime = millis();

  //If we don't currently have a working card, retry (throttled) rather than every loop
  if (!sdReady && (millis() - lastSdAttemptMs > SD_RETRY_INTERVAL_MS))
  {
    lastSdAttemptMs = millis();
    sdReady = initSD();
    if (sdReady) Serial.println("SD card (re)detected - resuming logging.");
  }

  if (sdReady)
  {
    if (!logFrameToSD(startTime))
    {
      //Write failed mid-run - most likely the card was just pulled. Drop out of
      //"ready" state; we'll retry on the next throttled attempt above.
      sdReady = false;
      Serial.println("SD write failed (card removed?). Will retry.");
    }
  }
  //else: no card present - frame is dropped, MLX90640 sampling continues normally

  //---- DHT11: read and log on its own ~1Hz-safe timer, independent of the thermal frame rate ----
  if (millis() - lastDhtReadMs >= DHT_READ_INTERVAL_MS)
  {
    lastDhtReadMs = millis();

    float humidity = dht.readHumidity();
    float tempC = dht.readTemperature();

    if (isnan(humidity) || isnan(tempC))
    {
      Serial.println("DHT11 read failed (check wiring).");
    }
    else if (sdReady)
    {
      if (!logDhtToSD(lastDhtReadMs, tempC, humidity))
      {
        sdReady = false;
        Serial.println("SD write failed (card removed?). Will retry.");
      }
    }
    //else: no card present - reading is dropped, will resume once the card returns
  }
}

//(Re)mounts the SD card and ensures the log file exists with a valid header.
//Safe to call repeatedly - SD.end() clears any stale state from a previous
//card before remounting, so this works whether the same card was reinserted
//or a different one was swapped in.
bool initSD()
{
  SD.end();
  delay(50); //give the card a moment to settle after CS is released
  if (!SD.begin(SD_CS_PIN))
    return false;

  if (!SD.exists(LOG_FILENAME))
  {
    File dataFile = SD.open(LOG_FILENAME, FILE_WRITE);
    if (!dataFile)
      return false;
    FileHeader header = { FILE_MAGIC, 768, TEMP_SCALE };
    dataFile.write((uint8_t *)&header, sizeof(header));
    dataFile.close();
  }

  if (!SD.exists(DHT_LOG_FILENAME))
  {
    File dhtFile = SD.open(DHT_LOG_FILENAME, FILE_WRITE);
    if (!dhtFile)
      return false;
    dhtFile.println("timestamp_ms,temperature_C,humidity_pct");
    dhtFile.close();
  }

  return true;
}

//Appends one binary FrameRecord (timestamp + 768 fixed-point pixel values) to the SD card log file.
//Returns true on success, false if the write failed (e.g. card was removed).
bool logFrameToSD(unsigned long timestamp)
{
  static FrameRecord record; //static so it isn't re-allocated on the stack every call

  record.timestamp_ms = (uint32_t)timestamp;
  for (int x = 0 ; x < 768 ; x++)
  {
    record.pixels[x] = floatToFixed(mlx90640To[x]);
  }

  File dataFile = SD.open(LOG_FILENAME, FILE_APPEND);
  if (!dataFile)
  {
    return false;
  }

  size_t written = dataFile.write((uint8_t *)&record, sizeof(record));
  dataFile.close(); //closing flushes the write, so data survives a sudden power loss

  return written == sizeof(record);
}

//Appends one CSV row (timestamp, temperature, humidity) to the DHT11 log file.
//Returns true on success, false if the write failed (e.g. card was removed).
bool logDhtToSD(unsigned long timestamp, float tempC, float humidity)
{
  File dhtFile = SD.open(DHT_LOG_FILENAME, FILE_APPEND);
  if (!dhtFile)
  {
    return false;
  }

  dhtFile.print(timestamp);
  dhtFile.print(",");
  dhtFile.print(tempC, 1);
  dhtFile.print(",");
  dhtFile.println(humidity, 1);
  dhtFile.close(); //closing flushes the write, so data survives a sudden power loss

  return true;
}

//Converts a temperature to a scaled, rounded int16_t (0.01C resolution)
int16_t floatToFixed(float tempC)
{
  return (int16_t)round(tempC * TEMP_SCALE);
}

//Returns true if the MLX90640 is detected on the I2C bus
boolean isConnected()
{
  Wire.beginTransmission((uint8_t)MLX90640_address);
  if (Wire.endTransmission() != 0)
    return (false); //Sensor did not ACK
  return (true);
}

