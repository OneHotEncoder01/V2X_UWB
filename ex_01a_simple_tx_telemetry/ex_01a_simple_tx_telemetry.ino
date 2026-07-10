#include "dw3000.h"

#define APP_NAME "SIMPLE TX v1.2 [TELEMETRY]"

// connection pins
const uint8_t PIN_RST = 27; // reset pin
const uint8_t PIN_IRQ = 34; // irq pin
const uint8_t PIN_SS = 4;   // spi select pin

/* Default communication configuration. We use default non-STS DW mode. */
static dwt_config_t config = {
    5,               /* Channel number. */
    DWT_PLEN_128,    /* Preamble length. Used in TX only. */
    DWT_PAC8,        /* Preamble acquisition chunk size. Used in RX only. */
    9,               /* TX preamble code. Used in TX only. */
    9,               /* RX preamble code. Used in RX only. */
    1,               /* 0 to use standard 8 symbol SFD, 1 to use non-standard 8 symbol, 2 for non-standard 16 symbol SFD and 3 for 4z 8 symbol SDF type */
    DWT_BR_6M8,      /* Data rate. */
    DWT_PHRMODE_STD, /* PHY header mode. */
    DWT_PHRRATE_STD, /* PHY header rate. */
    (129 + 8 - 8),   /* SFD timeout (preamble length + 1 + SFD length - PAC size). Used in RX only. */
    DWT_STS_MODE_OFF,
    DWT_STS_LEN_64,  /* STS length, see allowed values in Enum dwt_sts_lengths_e */
    DWT_PDOA_M0      /* PDOA mode off */
};

#define MAX_PAYLOAD 100

static uint8_t tx_msg[MAX_PAYLOAD];
uint16_t tx_len = 0;

#define FRAME_LENGTH (sizeof(tx_msg) + FCS_LEN)
#define TX_DELAY_MS 500

extern dwt_txconfig_t txconfig_options;

unsigned long msg_counter = 0;

int hexValue(char c)
{
  if (c >= '0' && c <= '9')
    return c - '0';
  if (c >= 'a' && c <= 'f')
    return c - 'a' + 10;
  if (c >= 'A' && c <= 'F')
    return c - 'A' + 10;
  return -1;
}

void setup()
{
  Serial.begin(115200);
  UART_init();
  test_run_info((unsigned char *)APP_NAME);

  /* Configure SPI rate, DW3000 supports up to 38 MHz */
  /* Reset DW IC */
  spiBegin(PIN_IRQ, PIN_RST);
  spiSelect(PIN_SS);

  delay(200);

  while (!dwt_checkidlerc())
  {
    test_run_info((unsigned char *)"IDLE FAILED01\r\n");
    while (100);
  }

  dwt_softreset();
  delay(200);

  while (!dwt_checkidlerc())
  {
    test_run_info((unsigned char *)"IDLE FAILED02\r\n");
    while (100);
  }

  if (dwt_initialise(DWT_DW_INIT) == DWT_ERROR)
  {
    test_run_info((unsigned char *)"INIT FAILED\r\n");
    while (100);
  }

  dwt_setleds(DWT_LEDS_ENABLE | DWT_LEDS_INIT_BLINK);

  if (dwt_configure(&config))
  {
    test_run_info((unsigned char *)"CONFIG FAILED\r\n");
    while (100);
  }

  dwt_configuretxrf(&txconfig_options);
}

void loop()
{
    if (!Serial.available())
    {
        delay(10);
        return;
    }

    unsigned long rx_timestamp = millis();
    String hex_msg = Serial.readStringUntil('\n');
    hex_msg.trim();

    // Validation
    if ((hex_msg.length() % 2) != 0)
    {
        Serial.println("ERR: odd hex length");
        return;
    }

    if ((hex_msg.length() / 2) > MAX_PAYLOAD)
    {
        Serial.println("ERR: payload too long");
        return;
    }

    tx_len = hex_msg.length() / 2;

    // Parse hex
    for (uint16_t i = 0; i < tx_len; i++)
    {
        int high = hexValue(hex_msg.charAt(i * 2));
        int low = hexValue(hex_msg.charAt(i * 2 + 1));

        if (high < 0 || low < 0)
        {
            Serial.println("ERR: invalid hex");
            return;
        }

        tx_msg[i] = (high << 4) | low;
    }

    // Transmit
    unsigned long tx_start = millis();
    dwt_writetxdata(tx_len, tx_msg, 0);
    dwt_writetxfctrl(tx_len + FCS_LEN, 0, 0);
    dwt_starttx(DWT_START_TX_IMMEDIATE);

    // Poll for TX complete
    while (!(dwt_read32bitreg(SYS_STATUS_ID) & SYS_STATUS_TXFRS_BIT_MASK))
    {
    }

    unsigned long tx_done = millis();
    dwt_write32bitreg(SYS_STATUS_ID, SYS_STATUS_TXFRS_BIT_MASK);

    // Enhanced telemetry response
    // Format: TX <payload_len> <seq> <rx_latency_ms> <tx_duration_ms>
    msg_counter++;
    unsigned long rx_latency = tx_start - rx_timestamp;
    unsigned long tx_duration = tx_done - tx_start;

    Serial.print("TX ");
    Serial.print(tx_len);
    Serial.print(" seq=");
    Serial.print(msg_counter);
    Serial.print(" rx_latency=");
    Serial.print(rx_latency);
    Serial.print("ms tx_dur=");
    Serial.print(tx_duration);
    Serial.println("ms");
}
